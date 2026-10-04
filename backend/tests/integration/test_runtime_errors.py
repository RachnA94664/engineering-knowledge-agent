"""What the runtime does when the AI provider misbehaves (all simulated, no network)."""

import httpx
import ollama
import openai
import pytest

from app.agents.runtime import AgentRuntime
from app.domain.errors import ServiceUnavailable
from app.services import changes
from tests.agents.fakes import ScriptedChatModel, call, runtime_with, say

REQUEST = httpx.Request("POST", "http://example.invalid")


def bad_request(message: str) -> openai.BadRequestError:
    return openai.BadRequestError(message, response=httpx.Response(400, request=REQUEST), body=None)


def test_a_provider_outage_becomes_service_unavailable_without_leaking_details(seeded):
    secret = "internal host db-7.corp and key sk-123"
    runtime, _ = runtime_with(openai.APIConnectionError(message=secret, request=REQUEST))

    with pytest.raises(ServiceUnavailable) as exc:
        runtime.run(seeded, "Show me REQ-001")

    assert "not available" in exc.value.message
    assert "sk-123" not in exc.value.message and "corp" not in exc.value.message


def test_other_provider_rejections_are_also_service_unavailable(seeded):
    runtime, _ = runtime_with(bad_request("context length exceeded"))
    with pytest.raises(ServiceUnavailable):
        runtime.run(seeded, "Show me REQ-001")


class FlakyProvider:
    """First model rejects `temperature`; after `drop_temperature()` the second one works."""

    def __init__(self, rejecting: ScriptedChatModel, working: ScriptedChatModel):
        self._models = [rejecting, working]
        self.dropped = 0

    def __call__(self):
        return self._models[min(self.dropped, 1)]

    def drop_temperature(self) -> bool:
        if self.dropped:
            return False
        self.dropped += 1
        return True


def test_a_model_that_rejects_temperature_is_retried_once_without_it(seeded):
    rejecting = ScriptedChatModel(
        bad_request("Unsupported value: 'temperature' does not support 0")
    )
    working = ScriptedChatModel(
        call("get_requirement", requirement_id="REQ-001"), say("REQ-001 is verified.")
    )
    provider = FlakyProvider(rejecting, working)

    result = AgentRuntime(provider).run(seeded, "Show me REQ-001")

    assert provider.dropped == 1
    assert result.grounded and [r["id"] for r in result.records] == ["REQ-001"]


def test_the_temperature_retry_cannot_repeat_a_write(seeded):
    """The rejection happens on the first AI call, before any tool ran, so nothing doubles."""
    rejecting = ScriptedChatModel(bad_request("'temperature' is not supported"))
    working = ScriptedChatModel(
        call("propose_requirement_change", requirement_id="REQ-007", status="implemented"),
        say("ok"),
    )
    AgentRuntime(FlakyProvider(rejecting, working)).run(seeded, "Set REQ-007 status to implemented")

    assert len(changes.list_pending_changes(seeded)) == 1  # one proposal, not two


def test_the_retry_happens_only_once(seeded):
    always_rejecting = ScriptedChatModel(
        bad_request("'temperature' unsupported"), bad_request("'temperature' unsupported")
    )
    provider = FlakyProvider(always_rejecting, always_rejecting)
    with pytest.raises(ServiceUnavailable):
        AgentRuntime(provider).run(seeded, "Show me REQ-001")
    assert provider.dropped == 1


# ---------- a local AI (Ollama) that is not running or too slow ----------


class LocalProvider:
    """Stands in for OllamaModelProvider: a model plus its helpful 'is Ollama running?' text."""

    unavailable_message = "the local AI (Ollama, model 'qwen2.5:3b') is not reachable."

    def __init__(self, model):
        self._model = model

    def __call__(self):
        return self._model


@pytest.mark.parametrize(
    "failure",
    [
        ConnectionError("Failed to connect to Ollama at http://localhost:11434"),
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        ollama.ResponseError("model 'qwen2.5:3b' not found, try pulling it first", 404),
    ],
)
def test_local_ai_failures_become_one_safe_message_with_a_hint(seeded, failure):
    runtime = AgentRuntime(LocalProvider(ScriptedChatModel(failure)))

    with pytest.raises(ServiceUnavailable) as exc:
        runtime.run(seeded, "Show me REQ-001")

    assert "Ollama" in exc.value.message  # tells the user what to check
    assert "localhost" not in exc.value.message and "pulling" not in exc.value.message
