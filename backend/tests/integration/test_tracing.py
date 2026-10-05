"""LangSmith tracing, tested END TO END with a fake LangSmith server on this machine.

Nothing here talks to the real LangSmith. The REAL agent graph runs with the REAL tracer, and a
tiny local HTTP server records everything the tracer tries to send.
"""

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.agents.runtime import AgentRuntime
from app.core.config import Settings
from app.core.tracing import CONNECT_TIMEOUT_MS, READ_TIMEOUT_MS, build_tracer
from tests.agents.fakes import ScriptedChatModel, call, say

FAKE_KEY = "lsv2_pt_TEST_KEY_that_must_never_appear_in_a_body"
QUESTION = "Show me REQ-001"
ANSWER = "REQ-001 is verified."


class FakeLangSmith:
    """Records every request a tracer makes to 'LangSmith'."""

    def __init__(self, status: int = 200):
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _record(self):
                length = int(self.headers.get("Content-Length") or 0)
                outer.requests.append(
                    {
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": self.rfile.read(length).decode("utf-8", errors="replace"),
                    }
                )
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")

            do_POST = do_GET = do_PATCH = _record

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    @property
    def run_posts(self) -> list[dict]:
        return [r for r in self.requests if r["path"].startswith("/runs")]

    def all_text(self) -> str:
        return "\n".join(r["body"] for r in self.requests)

    def runs(self) -> dict[str, dict]:
        """Merge the parts of every multipart upload into one dict per run."""
        merged: dict[str, dict] = {}
        for request in self.run_posts:
            boundary = re.search(r"boundary=(\S+)", request["headers"].get("content-type", ""))
            if not boundary:
                continue
            for part in request["body"].split("--" + boundary.group(1)):
                # Parts are named post.<id> (the run) or post.<id>.<field> for big fields that
                # LangSmith ships separately: inputs, outputs, extra (metadata lives here), ...
                header = re.search(r'name="(post|patch)\.([^."]+)(?:\.(\w+))?"', part)
                if not header or "\r\n\r\n" not in part:
                    continue
                try:
                    data = json.loads(part.split("\r\n\r\n", 1)[1].rsplit("\r\n", 1)[0])
                except ValueError:
                    continue
                run = merged.setdefault(header.group(2), {"tags": set()})
                if header.group(3):
                    run[header.group(3)] = data
                elif isinstance(data, dict):
                    run["tags"] |= set(data.get("tags") or [])
                    run.update({k: v for k, v in data.items() if k != "tags" and v is not None})
        return merged

    def run_names(self) -> set[str]:
        return {run.get("name") for run in self.runs().values()}


@pytest.fixture
def langsmith():
    server = FakeLangSmith()
    yield server
    server.stop()


def settings_for(server_url: str, **overrides) -> Settings:
    values = {
        "langsmith_tracing": True,
        "langsmith_api_key": FAKE_KEY,
        "langsmith_endpoint": server_url,
        "langsmith_project": "test-project",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # never read the developer's real .env


def wait_for(condition, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


def chat(session, tracer=None):
    """One real chat message through the real graph, with a scripted model."""
    model = ScriptedChatModel(call("get_requirement", requirement_id="REQ-001"), say(ANSWER))
    return AgentRuntime(lambda: model, tracer=tracer).run(session, QUESTION)


def traced_chat(session, server, **overrides):
    """Run a chat with tracing on and wait until the trace has reached the fake server."""
    tracer = build_tracer(settings_for(server.url, **overrides))
    result = chat(session, tracer)
    tracer.client.flush()
    assert wait_for(lambda: "finalize_query" in server.run_names()), "the trace never arrived"
    return result, tracer


# ---------- tracing ON ----------


def test_a_chat_message_is_traced_as_the_graph_with_its_tool_calls(seeded, langsmith):
    result, _ = traced_chat(seeded, langsmith)

    assert result.answer == ANSWER and result.grounded is True  # the user's answer is unchanged
    names = langsmith.run_names()
    # the dashboard shows the real flow: route -> agent -> AI call -> tool -> check
    assert {"chat", "route", "query_agent", "query_tools", "get_requirement"} <= names
    assert "finalize_query" in names
    assert "test-project" in langsmith.all_text()


def test_every_trace_is_tagged_with_the_intent_and_how_it_was_routed(seeded, langsmith):
    traced_chat(seeded, langsmith)

    root = next(r for r in langsmith.runs().values() if r.get("name") == "chat")
    assert {"engineering-knowledge-agent", "intent:query"} <= root["tags"]
    metadata = (root.get("extra") or {}).get("metadata", {})
    assert metadata.get("intent") == "query" and metadata.get("routed_by") == "rules"


def test_the_question_and_the_tool_arguments_are_visible_in_the_trace(seeded, langsmith):
    traced_chat(seeded, langsmith)
    text = langsmith.all_text()
    assert QUESTION in text and "get_requirement" in text and "REQ-001" in text


def test_the_api_key_is_only_ever_sent_as_a_header_never_in_a_body(seeded, langsmith):
    traced_chat(seeded, langsmith)

    assert langsmith.requests, "nothing was sent: the test would prove nothing"
    assert FAKE_KEY not in langsmith.all_text()
    assert any(r["headers"].get("x-api-key") == FAKE_KEY for r in langsmith.requests)


def test_no_database_objects_or_locks_are_sent(seeded, langsmith):
    traced_chat(seeded, langsmith)
    text = langsmith.all_text().lower()
    assert "sqlalchemy" not in text and "db_lock" not in text and "<session" not in text


def test_the_tracer_has_short_timeouts_and_a_retry_limit(langsmith):
    tracer = build_tracer(settings_for(langsmith.url))

    assert tracer.project_name == "test-project"
    assert tracer.client.timeout_ms == (CONNECT_TIMEOUT_MS, READ_TIMEOUT_MS)
    assert tracer.client.session.adapters["http://"].max_retries.total == 1  # then give up


# ---------- tracing OFF ----------


def test_tracing_off_sends_nothing_even_when_a_key_is_present(seeded, langsmith):
    tracer = build_tracer(settings_for(langsmith.url, langsmith_tracing=False))
    assert tracer is None

    result = chat(seeded, tracer)

    time.sleep(1)
    assert result.answer == ANSWER
    assert langsmith.requests == []  # not one request


def test_tracing_on_with_the_placeholder_key_stays_off(seeded, langsmith):
    tracer = build_tracer(settings_for(langsmith.url, langsmith_api_key="your-langsmith-key-here"))
    assert tracer is None

    result = chat(seeded, tracer)

    time.sleep(1)
    assert result.answer == ANSWER and langsmith.requests == []


def test_the_default_runtime_has_no_tracer_and_sends_nothing(seeded, langsmith):
    result = chat(seeded)  # exactly how every other test builds a runtime
    time.sleep(1)
    assert result.answer == ANSWER and langsmith.requests == []


# ---------- privacy switch ----------


def test_hide_data_sends_the_structure_but_not_the_text(seeded, langsmith):
    result, tracer = traced_chat(seeded, langsmith, langsmith_hide_data=True)

    assert result.answer == ANSWER  # the user still gets the answer
    assert {"route", "query_agent", "get_requirement"} <= langsmith.run_names()  # structure: yes
    text = langsmith.all_text()
    assert QUESTION not in text and ANSWER not in text  # the text: no


# ---------- tracing must never break or slow a request ----------


def test_an_unreachable_langsmith_never_breaks_or_slows_the_chat(seeded):
    started = time.time()
    tracer = build_tracer(settings_for("http://127.0.0.1:9"))  # nothing listens here
    setup_seconds = time.time() - started

    started = time.time()
    result = chat(seeded, tracer)
    chat_seconds = time.time() - started

    assert result.answer == ANSWER and result.grounded is True
    assert chat_seconds < 3  # the chat is not held up by the dead endpoint
    assert setup_seconds < 15  # even start-up is bounded by the short timeouts
    started = time.time()
    tracer.client.flush()
    assert time.time() - started < 30  # and flushing a dead endpoint gives up (does not hang)


def test_a_langsmith_that_rejects_every_request_never_breaks_the_chat(seeded):
    rejecting = FakeLangSmith(status=500)
    try:
        tracer = build_tracer(settings_for(rejecting.url))
        result = chat(seeded, tracer)
        tracer.client.flush()
    finally:
        rejecting.stop()

    assert result.answer == ANSWER and result.grounded is True
