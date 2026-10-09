"""The prompt loader, tested WITHOUT any network: LangSmith is replaced by a fake client."""

import logging

import pytest
from langchain_core.prompts import ChatPromptTemplate
from langsmith.utils import LangSmithConnectionError

from app.agents import prompt_loader
from app.agents.prompt_loader import (
    MAX_PROMPT_CHARS,
    PROMPT_NAMES,
    PromptError,
    langsmith_prompt_name,
    load_prompt,
    local_prompt,
    prompt_origin,
    system_text,
)
from app.core.config import Settings

KEY = "lsv2_pt_real_looking_key_123"


class FakeClient:
    """Stands in for ``langsmith.Client``: returns a prepared prompt, or raises."""

    def __init__(self, result=None, error=None):
        self.result, self.error, self.pulled = result, error, []

    def pull_prompt(self, name):
        self.pulled.append(name)
        if self.error:
            raise self.error
        return self.result


def make_settings(**overrides) -> Settings:
    base = {"prompt_source": "langsmith", "langsmith_api_key": KEY, "prompt_tag": ""}
    return Settings(**{**base, **overrides})


@pytest.fixture
def use(monkeypatch):
    """Install settings and a fake client; start each test with an empty cache."""

    def install(settings: Settings, client: FakeClient | None = None) -> FakeClient:
        client = client or FakeClient(ChatPromptTemplate.from_messages([("system", "REMOTE TEXT")]))
        monkeypatch.setattr(prompt_loader, "get_settings", lambda: settings)
        monkeypatch.setattr(prompt_loader, "_make_client", lambda _settings: client)
        load_prompt.cache_clear()
        prompt_loader._origins.clear()
        return client

    yield install
    load_prompt.cache_clear()
    prompt_loader._origins.clear()
    prompt_loader._unreachable = False


# ---------- where a prompt comes from ----------


def test_the_local_files_exist_for_every_agent_and_are_not_empty():
    for name in PROMPT_NAMES:
        assert len(local_prompt(name)) > 100


def test_source_local_never_contacts_langsmith(use):
    client = use(make_settings(prompt_source="local"))
    assert load_prompt("query") == local_prompt("query")
    assert client.pulled == [] and prompt_origin("query") == "local"


def test_source_langsmith_pulls_the_prompt_and_uses_its_text(use):
    client = use(make_settings())
    assert load_prompt("query") == "REMOTE TEXT"
    assert client.pulled == ["eka-query"] and prompt_origin("query") == "langsmith"


def test_a_tag_pins_the_version(use):
    client = use(make_settings(prompt_tag="production"))
    load_prompt("update")
    assert client.pulled == ["eka-update:production"]


def test_the_name_prefix_is_a_setting():
    settings = make_settings(prompt_name_prefix="team-", prompt_tag=" v2 ")
    assert langsmith_prompt_name(settings, "router") == "team-router:v2"


def test_a_prompt_is_pulled_once_and_cached(use):
    client = use(make_settings())
    assert load_prompt("analysis") == load_prompt("analysis")
    assert client.pulled == ["eka-analysis"]


# ---------- every way LangSmith can fail falls back to the file ----------


@pytest.mark.parametrize("key", ["", "   ", "your-langsmith-key-here"])
def test_without_a_real_key_the_local_file_is_used_and_nothing_is_pulled(use, key):
    client = use(make_settings(langsmith_api_key=key))
    assert load_prompt("query") == local_prompt("query")
    assert client.pulled == [] and prompt_origin("query") == "local"


@pytest.mark.parametrize(
    "error",
    [ConnectionError("network down"), TimeoutError("too slow"), RuntimeError("404 not found")],
)
def test_a_langsmith_failure_falls_back_to_the_file_and_logs_a_warning(use, caplog, error):
    use(make_settings(), FakeClient(error=error))
    with caplog.at_level(logging.WARNING, logger="app.prompts"):
        assert load_prompt("query") == local_prompt("query")
    assert prompt_origin("query") == "local"
    assert "using the local file" in caplog.text and type(error).__name__ in caplog.text


def test_after_one_connection_failure_the_other_prompts_do_not_wait_again(use):
    client = use(make_settings(), FakeClient(error=LangSmithConnectionError("unreachable")))
    for name in PROMPT_NAMES:
        assert load_prompt(name) == local_prompt(name)
    assert client.pulled == ["eka-query"]  # one timeout, not four


def test_a_missing_prompt_does_not_stop_the_others_from_loading(use):
    client = use(make_settings(), FakeClient(error=RuntimeError("404 not found")))
    load_prompt("query")
    load_prompt("update")
    assert client.pulled == ["eka-query", "eka-update"]


def test_the_api_key_never_reaches_the_logs(use, caplog):
    use(make_settings(), FakeClient(error=RuntimeError(f"auth failed for key {KEY}")))
    with caplog.at_level(logging.DEBUG, logger="app.prompts"):
        load_prompt("query")
    assert KEY not in caplog.text and "<hidden>" in caplog.text


@pytest.mark.parametrize(
    "template,reason",
    [
        (ChatPromptTemplate.from_messages([("system", "Hi {question}")]), "template variables"),
        (
            ChatPromptTemplate.from_messages([("system", "rules"), ("human", "hello")]),
            "keep only the System message",
        ),
        (ChatPromptTemplate.from_messages([("system", "   ")]), "it is empty"),
        (
            ChatPromptTemplate.from_messages([("system", "x" * (MAX_PROMPT_CHARS + 1))]),
            "the limit is",
        ),
    ],
)
def test_a_prompt_with_the_wrong_shape_is_rejected_and_the_file_is_used(
    use, caplog, template, reason
):
    use(make_settings(), FakeClient(template))
    with caplog.at_level(logging.WARNING, logger="app.prompts"):
        assert load_prompt("query") == local_prompt("query")
    assert prompt_origin("query") == "local" and "PromptError" in caplog.text
    assert reason in caplog.text  # the log says WHY, so the cause can be fixed


def test_system_text_joins_several_system_messages():
    template = ChatPromptTemplate.from_messages([("system", "one"), ("system", "two")])
    assert system_text(template) == "one\n\ntwo"


def test_system_text_rejects_variables_with_a_helpful_message():
    with pytest.raises(PromptError, match="template variables"):
        system_text(ChatPromptTemplate.from_messages([("system", "Hi {name}")]))
