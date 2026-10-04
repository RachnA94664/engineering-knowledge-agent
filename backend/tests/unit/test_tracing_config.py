"""When is LangSmith tracing on? These rules decide whether ANYTHING leaves the machine."""

import os

import pytest

from app.core.config import Settings
from app.core.tracing import build_tracer, configure_tracing, tag_current_run, tracing_requested

REAL_LOOKING_KEY = "lsv2_pt_0123456789abcdef"


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)  # never read the developer's real .env


@pytest.fixture
def clean_env():
    """configure_tracing edits the real process environment, so always put it back."""
    prefixes = ("LANGSMITH", "LANGCHAIN")
    saved = {n: v for n, v in os.environ.items() if n.startswith(prefixes)}
    for name in saved:
        del os.environ[name]
    yield
    for name in [n for n in os.environ if n.startswith(prefixes)]:
        del os.environ[name]
    os.environ.update(saved)


# ---------- is tracing requested? ----------


def test_tracing_is_off_by_default():
    assert tracing_requested(settings()) is False


def test_the_flag_alone_is_not_enough():
    assert tracing_requested(settings(langsmith_tracing=True)) is False


def test_a_key_alone_is_not_enough():
    assert tracing_requested(settings(langsmith_api_key=REAL_LOOKING_KEY)) is False


def test_the_placeholder_from_env_example_does_not_count_as_a_key():
    s = settings(langsmith_tracing=True, langsmith_api_key="your-langsmith-key-here")
    assert tracing_requested(s) is False


def test_a_blank_key_does_not_count():
    assert tracing_requested(settings(langsmith_tracing=True, langsmith_api_key="   ")) is False


def test_flag_plus_real_key_turns_tracing_on():
    s = settings(langsmith_tracing=True, langsmith_api_key=REAL_LOOKING_KEY)
    assert tracing_requested(s) is True


# ---------- no tracer unless everything is in place ----------


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"langsmith_tracing": True},
        {"langsmith_api_key": REAL_LOOKING_KEY},
        {"langsmith_tracing": True, "langsmith_api_key": "your-langsmith-key-here"},
        {"langsmith_tracing": True, "langsmith_api_key": "  "},
        {"langsmith_tracing": False, "langsmith_api_key": REAL_LOOKING_KEY},
    ],
)
def test_no_tracer_is_built_unless_the_flag_and_a_real_key_are_both_present(overrides):
    assert build_tracer(settings(**overrides)) is None


# ---------- implicit switches are always forced off ----------


def test_every_implicit_switch_is_forced_off(clean_env):
    os.environ["LANGSMITH_TRACING"] = "true"  # something outside tried to turn it on
    os.environ["LANGCHAIN_TRACING_V2"] = "true"

    configure_tracing(settings())

    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
    assert os.environ["LANGCHAIN_TRACING"] == "false"


def test_even_when_tracing_is_on_the_implicit_switches_stay_off(clean_env):
    """Traces come only from OUR tracer (with its timeouts and privacy switch)."""
    s = settings(langsmith_tracing=True, langsmith_api_key=REAL_LOOKING_KEY)

    assert configure_tracing(s) is True  # our tracer will be used ...

    assert os.environ["LANGSMITH_TRACING"] == "false"  # ... but nothing traces by itself


def test_the_api_key_is_never_copied_into_the_environment(clean_env):
    configure_tracing(settings(langsmith_tracing=True, langsmith_api_key=REAL_LOOKING_KEY))
    assert "LANGSMITH_API_KEY" not in os.environ
    assert REAL_LOOKING_KEY not in os.environ.values()


def test_a_flag_without_a_real_key_is_reported_off(clean_env):
    assert configure_tracing(settings(langsmith_tracing=True)) is False


# ---------- tagging a run ----------


def test_tagging_does_nothing_and_never_raises_when_there_is_no_trace():
    tag_current_run(None, ["intent:query"], {"intent": "query"})  # no run is being traced
    tag_current_run({}, ["intent:query"], {"intent": "query"})
    tag_current_run({"callbacks": object()}, ["intent:query"], {"intent": "query"})


def test_the_test_suite_itself_never_traces():
    """conftest forces tracing off so a developer's real .env cannot make tests send data."""
    assert os.environ["LANGSMITH_TRACING"] == "false"
