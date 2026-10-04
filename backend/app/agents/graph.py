"""The LangGraph agent graph: one run per chat message.

    START -> route -+-> refuse ------------------------------------------> END
                    +-> query_agent  <-> query_tools  -> finalize_query ---> END
                    +-> update_agent <-> update_tools -> finalize_update --> END

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
from app.agents.router import route_by_rules, route_with_llm
from app.agents.tools import PROPOSE_CHANGE, READ_TOOLS, UPDATE_TOOLS

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


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message_text(message.content)
    return ""


def _limit_hit(state: AgentState) -> bool:
    """True if the model kept asking for tools after we ran out of rounds."""
    last: BaseMessage = state["messages"][-1]
    return bool(getattr(last, "tool_calls", None)) and state.get("rounds", 0) > MAX_ROUNDS


# ---------- nodes ----------


def make_route_node(get_model: ModelFactory) -> Callable:
    def route_node(state: AgentState, config) -> dict:
        text = _last_human_text(state)
        decision = route_by_rules(text)  # free and predictable; no AI involved
        if decision is None:
            decision = route_with_llm(get_model(), text, config)  # only for unclear messages
        return {"intent": decision.intent, "reason": decision.reason, "rounds": 0}

    return route_node


def refuse_node(state: AgentState) -> dict:
    """Refusals are written by code. The AI is never asked to explain a refusal."""
    if state["intent"] == "refused":
        return {"answer": f"I can't do that: {state['reason']}.", "grounded": True}
    return {"answer": answers.OUT_OF_SCOPE_ANSWER, "grounded": True}


def make_agent_node(
    get_model: ModelFactory, system_prompt: str, tools: Sequence[StructuredTool]
) -> Callable:
    """The chat model, bound to ONLY this agent's tools."""

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


def after_agent(state: AgentState) -> str:
    """Run tools if the model asked for them (and we still have rounds left), else finish."""
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None) and not _limit_hit(state):
        return "tools"
    return "finalize"


def finalize_query(state: AgentState) -> dict:
    """The grounding check. The answer is shown only if the database backs it."""
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
    change = event.result["change"]
    steps = "; ".join(
        f"{f}: {v['old']!r} -> {v['new']!r}" for f, v in event.result["preview"].items()
    )
    return f"Proposed change #{change['id']} for {change['entity_id']} ({steps})."


def finalize_update(state: AgentState) -> dict:
    """When a proposal was saved, the reply is written HERE, from the tool result.

    That way the answer can never claim "done" when nothing was applied.
    """
    proposals = [e for e in tool_events(state["messages"]) if e.name == PROPOSE_CHANGE.name]
    if proposals:
        lines = [
            _describe(e) if e.ok else f"I could not propose that: {e.error}" for e in proposals
        ]
        if any(e.ok for e in proposals):
            lines.append(
                "Nothing has been changed yet. Confirm or reject each proposal in the app."
            )
        return {"answer": " ".join(lines), "grounded": True}
    if _limit_hit(state):
        return {"answer": answers.TOO_MANY_STEPS_UPDATE_ANSWER, "grounded": False}
    return {"answer": answers.NEEDS_DETAILS_ANSWER, "grounded": False}


# ---------- wiring ----------


def pick_lane(state: AgentState) -> str:
    intent = state["intent"]
    if intent in ("refused", "out_of_scope"):
        return "refuse"
    return "update" if intent == "update" else "query"


def build_graph(get_model: ModelFactory):
    """Create the compiled graph. `get_model` returns the chat model (real or scripted)."""
    graph = StateGraph(AgentState)

    graph.add_node("route", make_route_node(get_model))
    graph.add_node("refuse", refuse_node)

    graph.add_node("query_agent", make_agent_node(get_model, load_prompt("query"), READ_TOOLS))
    graph.add_node("query_tools", ToolNode(list(READ_TOOLS), handle_tool_errors=True))
    graph.add_node("finalize_query", finalize_query)

    graph.add_node("update_agent", make_agent_node(get_model, load_prompt("update"), UPDATE_TOOLS))
    graph.add_node("update_tools", ToolNode(list(UPDATE_TOOLS), handle_tool_errors=True))
    graph.add_node("finalize_update", finalize_update)

    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route", pick_lane, {"refuse": "refuse", "query": "query_agent", "update": "update_agent"}
    )
    graph.add_edge("refuse", END)

    for lane in ("query", "update"):
        graph.add_conditional_edges(
            f"{lane}_agent", after_agent, {"tools": f"{lane}_tools", "finalize": f"finalize_{lane}"}
        )
        graph.add_edge(f"{lane}_tools", f"{lane}_agent")
        graph.add_edge(f"finalize_{lane}", END)

    return graph.compile(name="knowledge_agent")
