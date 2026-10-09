"""The LangGraph agent graph: one run per chat message.

    START -> route -+-> refuse ------------------------------------------> END
                    +-> query_agent  <-> query_tools  -> finalize_query ---> END
                    +-> update_prepare -+-> update_tools -> finalize_update -> END   (rules)
                    |                   +-> update_agent <-> update_tools
                    |                                    -> finalize_update -> END   (AI)
                    +-> analysis_prepare -+-> analysis_tools -> finalize_analysis -> END (rules)
                                          +-> analysis_agent <-> analysis_tools
                                                          -> finalize_analysis -> END (AI)

LangGraph runs the graph (nodes, edges, tool execution, tracing). The SAFETY RULES are
ordinary code inside the nodes: refusals before any AI call, each agent's tool allow-list,
the round and call limits, the grounding check, and replies written by code.
"""

from collections.abc import Callable, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agents import answers
from app.agents.events import (
    ToolEvent,
    evidence_texts,
    message_text,
    tool_events,
)
from app.agents.grounding import ungrounded_ids
from app.agents.llm import ModelFactory
from app.agents.prompt_loader import load_prompt
from app.agents.router import REQ_ID_FOUND, route_by_rules, route_with_llm
from app.agents.tools import (
    ANALYSIS_TOOLS,
    GET_IMPACT,
    PROPOSE_CHANGE,
    READ_TOOLS,
    UPDATE_TOOLS,
)
from app.agents.update_parser import parse_simple_update
from app.core.tracing import tag_current_run

MAX_ROUNDS = 4  # rounds of tool use per message
MAX_CALLS_PER_STEP = 4  # tool calls the model may make in one round
RECURSION_LIMIT = 30  # LangGraph's own hard stop on a runaway graph (a backstop)


class AgentState(MessagesState):
    """What flows through the graph. `messages` comes from MessagesState."""

    intent: str  # query | update | out_of_scope | refused
    reason: str  # why the router chose a refusal
    rounds: int  # how many times the agent has asked for tools
    answer: str  # the final answer shown to the user
    grounded: bool  # True if the answer is backed by database results
    direct: bool  # True if plain rules (not the AI) prepared the tool call


def _last_human_text(state: AgentState) -> str:
    """Find what the user last wrote.

    Args:
        state: The graph state.

    Returns:
        The text of the newest human message, or an empty string if there is none.
    """
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message_text(message.content)
    return ""


def _limit_hit(state: AgentState) -> bool:
    """Tell whether the model kept asking for tools after we ran out of rounds.

    Args:
        state: The graph state.

    Returns:
        True if the last message still asks for tools and more than ``MAX_ROUNDS`` rounds ran.
    """
    last: BaseMessage = state["messages"][-1]
    return bool(getattr(last, "tool_calls", None)) and state.get("rounds", 0) > MAX_ROUNDS


# ---------- nodes ----------


def make_route_node(get_model: ModelFactory) -> Callable:
    """Build the node that decides what a message is asking for.

    The node tries the keyword rules first (free and predictable) and asks the AI only for a
    message the rules cannot place. It also tags the LangSmith trace with the intent.

    Args:
        get_model: Returns the chat model (real or scripted). Only called if the rules cannot
            decide, so a refused request needs no AI at all.

    Returns:
        The graph node. It sets ``intent``, ``reason`` and resets ``rounds``.
    """

    def route_node(state: AgentState, config) -> dict:
        text = _last_human_text(state)
        decision = route_by_rules(text)  # free and predictable; no AI involved
        if decision is None:
            decision = route_with_llm(get_model(), text, config)  # only for unclear messages
        # In the LangSmith dashboard: filter runs by intent, and see how it was decided.
        tag_current_run(
            config,
            [f"intent:{decision.intent}"],
            {"intent": decision.intent, "routed_by": "ai" if decision.used_llm else "rules"},
        )
        return {"intent": decision.intent, "reason": decision.reason, "rounds": 0}

    return route_node


def refuse_node(state: AgentState) -> dict:
    """Write the reply to a refused or off-topic message. The AI is never asked to explain.

    Args:
        state: The graph state (``intent`` is ``refused`` or ``out_of_scope``).

    Returns:
        The state update: a fixed ``answer`` written by code, marked ``grounded``.
    """
    if state["intent"] == "refused":
        return {"answer": f"I can't do that: {state['reason']}.", "grounded": True}
    return {"answer": answers.OUT_OF_SCOPE_ANSWER, "grounded": True}


def make_agent_node(
    get_model: ModelFactory, system_prompt: str, tools: Sequence[StructuredTool]
) -> Callable:
    """Build an agent node: the chat model, bound to ONLY this agent's tools.

    Args:
        get_model: Returns the chat model (real or scripted).
        system_prompt: The agent's system prompt (from LangSmith or the local file).
        tools: The only tools this agent may call. An agent cannot use any other tool.

    Returns:
        The graph node. It asks the model what to do next, counts a round whenever the model
        asks for tools, and keeps at most ``MAX_CALLS_PER_STEP`` of those calls.
    """

    def agent_node(state: AgentState, config) -> dict:
        model = get_model().bind_tools(list(tools))
        response = model.invoke([SystemMessage(content=system_prompt), *state["messages"]], config)
        update: dict = {}
        calls = list(response.tool_calls) if isinstance(response, AIMessage) else []
        if calls:
            update["rounds"] = state.get("rounds", 0) + 1
            if len(calls) > MAX_CALLS_PER_STEP:  # too many at once: only the first few run
                response = response.model_copy(update={"tool_calls": calls[:MAX_CALLS_PER_STEP]})
        update["messages"] = [response]
        return update

    return agent_node


def update_prepare_node(state: AgentState) -> dict:
    """A simple change command ("Set REQ-006 priority to high") is read by plain rules.

    The AI is then not needed: the proposal goes through the same tool and the same checks.
    Anything unusual falls through to the AI agent.

    Args:
        state: The graph state.

    Returns:
        ``{"direct": False}`` when the AI must handle the message; otherwise a ready-made
        tool call for ``propose_requirement_change`` with ``direct`` set to True.
    """
    arguments = parse_simple_update(_last_human_text(state))
    if arguments is None:
        return {"direct": False}
    call = AIMessage(
        content="",
        tool_calls=[
            {"name": PROPOSE_CHANGE.name, "args": arguments, "id": "rules-1", "type": "tool_call"}
        ],
    )
    return {"messages": [call], "direct": True, "rounds": 1}


def analysis_prepare_node(state: AgentState) -> dict:
    """What is the impact of REQ-009? This names exactly one requirement: read its stored report.

    The report was written by rules when the change was confirmed, so no AI is needed to look
    it up or to describe it. Unusual questions (several requirements, no id) go to the AI.

    Args:
        state: The graph state.

    Returns:
        ``{"direct": False}`` when the AI must handle the message; otherwise a ready-made
        tool call for ``get_impact`` with ``direct`` set to True.
    """
    ids = sorted({m.upper() for m in REQ_ID_FOUND.findall(_last_human_text(state))})
    if len(ids) != 1:
        return {"direct": False}
    call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": GET_IMPACT.name,
                "args": {"requirement_id": ids[0]},
                "id": "rules-1",
                "type": "tool_call",
            }
        ],
    )
    return {"messages": [call], "direct": True, "rounds": 1}


def after_prepare(state: AgentState) -> str:
    """Choose the next step after a rules-based preparation.

    Args:
        state: The graph state.

    Returns:
        ``"tools"`` if rules already made the tool call, otherwise ``"agent"``.
    """
    return "tools" if state.get("direct") else "agent"


def after_direct_tools(state: AgentState) -> str:
    """After a rules-made tool call there is nothing for the AI to add: finish.

    Args:
        state: The graph state.

    Returns:
        ``"finalize"`` for a rules-made call, otherwise ``"agent"``.
    """
    return "finalize" if state.get("direct") else "agent"


def after_agent(state: AgentState) -> str:
    """Run tools if the model asked for them (and we still have rounds left), else finish.

    Args:
        state: The graph state.

    Returns:
        ``"tools"`` or ``"finalize"``.
    """
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None) and not _limit_hit(state):
        return "tools"
    return "finalize"


def finalize_query(state: AgentState) -> dict:
    """Apply the grounding check: the answer is shown only if the database backs it.

    Args:
        state: The graph state, with the model's final message and the tool results.

    Returns:
        The state update: the ``answer`` to show and whether it is ``grounded``. An answer
        with no tool lookup behind it, or one that names an ID no tool returned, is replaced
        by a fixed message written by code.
    """
    if _limit_hit(state):
        return {"answer": answers.TOO_MANY_STEPS_ANSWER, "grounded": False}

    messages = state["messages"]
    text = message_text(messages[-1].content).strip() if messages else ""
    evidence = evidence_texts(messages)

    if not evidence or not text:  # an answer with no database lookup behind it is never shown
        return {"answer": answers.NO_DATA_ANSWER, "grounded": False}
    if ungrounded_ids(text, evidence):  # it mentions an id no tool returned: invented
        return {"answer": answers.UNVERIFIED_ANSWER, "grounded": False}
    return {"answer": text, "grounded": True}


def _describe(event: ToolEvent) -> str:
    """Describe a saved proposal in one sentence.

    Args:
        event: The successful ``propose_requirement_change`` tool result.

    Returns:
        For example ``Proposed change #4 for REQ-006 (priority: 'medium' -> 'high').``
    """
    change = event.result["change"]
    steps = "; ".join(
        f"{f}: {v['old']!r} -> {v['new']!r}" for f, v in event.result["preview"].items()
    )
    return f"Proposed change #{change['id']} for {change['entity_id']} ({steps})."


def finalize_update(state: AgentState) -> dict:
    """When a proposal was saved, the reply is written HERE, from the tool result.

    That way the answer can never claim "done" when nothing was applied.

    Args:
        state: The graph state, with the tool results.

    Returns:
        The state update: the ``answer`` and whether it is ``grounded``. A successful proposal
        always ends with "Nothing has been changed yet".
    """
    proposals = [e for e in tool_events(state["messages"]) if e.name == PROPOSE_CHANGE.name]
    if proposals:
        recovered = any(e.ok for e in proposals)
        lines = []
        for e in proposals:
            if e.ok:
                lines.append(_describe(e))
            elif e.code == "invalid_call":
                # The AI's call was malformed. If it then got a proposal through, say nothing
                # about the glitch; otherwise explain simply, with no framework internals.
                if not recovered:
                    lines.append(answers.UPDATE_NOT_UNDERSTOOD_ANSWER)
            else:
                lines.append(f"I could not propose that: {e.error}.")
        lines = list(dict.fromkeys(lines))  # the same sentence once, not three times
        if any(e.ok for e in proposals):
            lines.append(
                "Nothing has been changed yet. Confirm or reject each proposal in the app."
            )
        return {"answer": " ".join(lines), "grounded": True}
    if _limit_hit(state):
        return {"answer": answers.TOO_MANY_STEPS_UPDATE_ANSWER, "grounded": False}
    return {"answer": answers.NEEDS_DETAILS_ANSWER, "grounded": False}


def finalize_analysis(state: AgentState) -> dict:
    """Describe the stored impact report.

    When rules made the lookup, the answer is written HERE from the report itself, so it can
    never contain an invented test, risk or level. When the AI made the lookup (an unusual
    question), its text goes through the same grounding check as every other answer.

    Args:
        state: The graph state, with the tool results.

    Returns:
        The state update: the ``answer`` and whether it is ``grounded``.
    """
    if not state.get("direct"):
        return finalize_query(state)
    events = [e for e in tool_events(state["messages"]) if e.name == GET_IMPACT.name]
    event = events[-1]
    if not event.ok:  # e.g. "no impact report exists for REQ-009 yet: a confirmed change ..."
        return {"answer": f"{event.error}.", "grounded": True}
    report = event.result
    answer = (
        f"Latest confirmed change to {report['requirement_id']} "
        f"(change #{report['change_id']}): {report['summary']}"
    )
    return {"answer": answer, "grounded": True}


# ---------- wiring ----------


def pick_lane(state: AgentState) -> str:
    """Choose which specialist handles the message, from the routed intent.

    Args:
        state: The graph state (``intent`` has been set by the route node).

    Returns:
        ``"refuse"``, ``"analysis"``, ``"update"`` or ``"query"``.
    """
    intent = state["intent"]
    if intent in ("refused", "out_of_scope"):
        return "refuse"
    if intent == "analysis":
        return "analysis"
    return "update" if intent == "update" else "query"


def build_graph(get_model: ModelFactory):
    """Create the compiled agent graph (see the diagram at the top of this file).

    The system prompts are loaded here, once per process, through ``load_prompt``.

    Args:
        get_model: Returns the chat model (real or scripted for tests).

    Returns:
        The compiled LangGraph graph, ready to be invoked once per chat message.
    """
    graph = StateGraph(AgentState)

    graph.add_node("route", make_route_node(get_model))
    graph.add_node("refuse", refuse_node)

    graph.add_node("query_agent", make_agent_node(get_model, load_prompt("query"), READ_TOOLS))
    graph.add_node("query_tools", ToolNode(list(READ_TOOLS), handle_tool_errors=True))
    graph.add_node("finalize_query", finalize_query)

    graph.add_node("update_prepare", update_prepare_node)
    graph.add_node("update_agent", make_agent_node(get_model, load_prompt("update"), UPDATE_TOOLS))
    graph.add_node("update_tools", ToolNode(list(UPDATE_TOOLS), handle_tool_errors=True))
    graph.add_node("finalize_update", finalize_update)

    graph.add_node("analysis_prepare", analysis_prepare_node)
    graph.add_node(
        "analysis_agent", make_agent_node(get_model, load_prompt("analysis"), ANALYSIS_TOOLS)
    )
    graph.add_node("analysis_tools", ToolNode(list(ANALYSIS_TOOLS), handle_tool_errors=True))
    graph.add_node("finalize_analysis", finalize_analysis)

    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        pick_lane,
        {
            "refuse": "refuse",
            "query": "query_agent",
            "update": "update_prepare",
            "analysis": "analysis_prepare",
        },
    )
    graph.add_edge("refuse", END)

    # Query lane: the AI asks for tools until it can answer, then the grounding check runs.
    graph.add_conditional_edges(
        "query_agent", after_agent, {"tools": "query_tools", "finalize": "finalize_query"}
    )
    graph.add_edge("query_tools", "query_agent")
    graph.add_edge("finalize_query", END)

    # Update lane: rules first; the AI only when the command is not simple.
    graph.add_conditional_edges(
        "update_prepare", after_prepare, {"tools": "update_tools", "agent": "update_agent"}
    )
    graph.add_conditional_edges(
        "update_agent", after_agent, {"tools": "update_tools", "finalize": "finalize_update"}
    )
    graph.add_conditional_edges(
        "update_tools", after_direct_tools, {"agent": "update_agent", "finalize": "finalize_update"}
    )
    graph.add_edge("finalize_update", END)

    # Analysis lane: rules read the stored report; the AI only for unusual questions.
    graph.add_conditional_edges(
        "analysis_prepare", after_prepare, {"tools": "analysis_tools", "agent": "analysis_agent"}
    )
    graph.add_conditional_edges(
        "analysis_agent", after_agent, {"tools": "analysis_tools", "finalize": "finalize_analysis"}
    )
    graph.add_conditional_edges(
        "analysis_tools",
        after_direct_tools,
        {"agent": "analysis_agent", "finalize": "finalize_analysis"},
    )
    graph.add_edge("finalize_analysis", END)

    return graph.compile(name="knowledge_agent")
