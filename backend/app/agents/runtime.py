"""Run the agent graph for one chat message and return a safe, structured result."""

import logging
import threading

import openai
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from sqlalchemy.orm import Session

from app.agents import answers
from app.agents.events import collect_records, tool_events, tool_trace
from app.agents.graph import RECURSION_LIMIT, build_graph
from app.agents.llm import DEFAULT_UNAVAILABLE_MESSAGE, PROVIDER_ERRORS, ModelFactory
from app.agents.tools import PROPOSE_CHANGE
from app.agents.types import AgentResult
from app.domain.errors import ServiceUnavailable, ValidationError

logger = logging.getLogger("app.agents")

MAX_MESSAGE_CHARS = 1000


class AgentRuntime:
    def __init__(self, get_model: ModelFactory):
        self._get_model = get_model
        self._graph = build_graph(get_model)

    def run(self, session: Session, message: str) -> AgentResult:
        text = (message or "").strip()
        if not text:
            raise ValidationError("the message must not be empty")
        if len(text) > MAX_MESSAGE_CHARS:
            raise ValidationError(f"the message must be at most {MAX_MESSAGE_CHARS} characters")

        try:
            state = self._invoke(session, text)
        except GraphRecursionError:
            # The graph's own backstop fired: stop cleanly instead of looping.
            return AgentResult(answers.TOO_MANY_STEPS_ANSWER, "query", grounded=False)
        return self._to_result(state)

    def _invoke(self, session: Session, text: str, *, retry_without_temperature: bool = True):
        config = {
            # The database session (and a lock for it) travel in the run config. Tools read them
            # from here; the AI never sees them and cannot choose them.
            "configurable": {"session": session, "db_lock": threading.Lock()},
            "recursion_limit": RECURSION_LIMIT,
            "run_name": "chat",
        }
        try:
            return self._graph.invoke({"messages": [HumanMessage(content=text)]}, config)
        except openai.BadRequestError as exc:
            # Some models reject `temperature`. That is rejected on the very FIRST AI call,
            # before any tool has run, so retrying from the start cannot repeat a write.
            drop = getattr(self._get_model, "drop_temperature", None)
            if retry_without_temperature and "temperature" in str(exc).lower() and drop and drop():
                return self._invoke(session, text, retry_without_temperature=False)
            logger.error("AI request rejected: %s", type(exc).__name__)
            raise ServiceUnavailable(self._unavailable_message()) from exc
        except PROVIDER_ERRORS as exc:
            # Whichever AI is in use (OpenAI, Ollama, ...): log the kind of failure for us and
            # tell the user nothing sensitive (the original message is never shown).
            logger.error("AI request failed: %s", type(exc).__name__)
            raise ServiceUnavailable(self._unavailable_message()) from exc

    def _unavailable_message(self) -> str:
        """A fixed, safe sentence. A local provider may add a helpful hint (is Ollama running?)."""
        return getattr(self._get_model, "unavailable_message", DEFAULT_UNAVAILABLE_MESSAGE)

    @staticmethod
    def _to_result(state: dict) -> AgentResult:
        intent = state["intent"]
        events = tool_events(state["messages"])
        pending = []
        if intent == "update":
            pending = [
                {"change": e.result["change"], "preview": e.result["preview"]}
                for e in events
                if e.name == PROPOSE_CHANGE.name and e.ok
            ]
        return AgentResult(
            answer=state["answer"],
            intent=intent,
            grounded=state.get("grounded", False),
            refused=intent in ("refused", "out_of_scope"),
            records=collect_records(events),
            tool_calls=tool_trace(events),
            pending_changes=pending,
        )
