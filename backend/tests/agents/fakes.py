"""A scripted fake chat model for tests: no key, no network, no cost, same answer every time.

LangChain's built-in fake models cannot take part in tool calling (they do not implement
`bind_tools`), so we use our own.
"""

import itertools

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from app.agents.runtime import AgentRuntime

_ids = itertools.count(1)


class ScriptedChatModel(BaseChatModel):
    """Returns the prepared responses in order and records every call it receives.

    If the code calls the AI MORE often than the test prepared for, it fails loudly:
    that is how tests prove "the AI was never asked" (use `ScriptedChatModel()` with nothing).
    """

    # Private state is SHARED between copies, so `bind_tools()` returns a model that writes
    # to the same script and call log.
    _script: list = PrivateAttr(default_factory=list)
    _calls: list = PrivateAttr(default_factory=list)
    _bound: list = PrivateAttr(default_factory=list)

    def __init__(self, *responses):
        super().__init__()
        self._script.extend(responses)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def calls(self) -> list[dict]:
        """Every call: {"messages": [...], "tools": [names of tools bound for that call]}."""
        return self._calls

    def bind_tools(self, tools, **kwargs):
        clone = self.model_copy()
        clone._bound = [getattr(t, "name", str(t)) for t in tools]
        return clone

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self._calls.append({"messages": list(messages), "tools": list(self._bound)})
        if not self._script:
            raise AssertionError("the AI was called more often than this test expected")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return ChatResult(generations=[ChatGeneration(message=item)])


def say(text: str) -> AIMessage:
    """The AI answers with plain text."""
    return AIMessage(content=text)


def _tool_call(name: str, arguments: dict) -> dict:
    return {"name": name, "args": arguments, "id": f"call_{next(_ids)}", "type": "tool_call"}


def call(name: str, **arguments) -> AIMessage:
    """The AI asks us to run one tool."""
    return AIMessage(content="", tool_calls=[_tool_call(name, arguments)])


def calls(*specs: tuple[str, dict]) -> AIMessage:
    """The AI asks for several tools in one go."""
    return AIMessage(content="", tool_calls=[_tool_call(n, a) for n, a in specs])


def runtime_with(*responses) -> tuple[AgentRuntime, ScriptedChatModel]:
    """The real graph, driven by a scripted model. Returns (runtime, model) for assertions."""
    model = ScriptedChatModel(*responses)
    return AgentRuntime(lambda: model), model
