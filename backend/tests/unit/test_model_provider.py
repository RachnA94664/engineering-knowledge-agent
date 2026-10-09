"""The OpenAI model provider, tested WITHOUT any network (no call is ever made)."""

import pytest

from app.agents.llm import (
    GroqModelProvider,
    OllamaModelProvider,
    OpenAIModelProvider,
    build_model_provider,
)
from app.core.config import get_settings
from app.domain.errors import ServiceUnavailable


def provider(key="test-key"):
    return OpenAIModelProvider(api_key=key, model="gpt-x", timeout=5, max_output_tokens=100)


def test_no_api_key_means_service_unavailable_not_a_crash():
    with pytest.raises(ServiceUnavailable) as exc:
        provider(key="")()
    assert "OPENAI_API_KEY" in exc.value.message  # names the setting, never a key


def test_the_model_is_built_with_our_cost_and_safety_limits():
    model = provider()()
    assert model.model_name == "gpt-x"
    assert model.temperature == 0
    assert model.max_retries == 2
    assert model.request_timeout == 5
    assert model.max_tokens == 100  # the cap on one answer


def test_the_model_is_created_once_and_reused():
    p = provider()
    assert p() is p()


def test_temperature_can_be_dropped_once_for_models_that_reject_it():
    p = provider()
    first = p()
    assert p.drop_temperature() is True
    second = p()
    assert second is not first and second.temperature is None
    assert p.drop_temperature() is False  # nothing left to drop: no endless retries


# ---------- Ollama: a free model running on your own PC ----------


def ollama_provider():
    return OllamaModelProvider(
        model="qwen2.5:3b",
        base_url="http://localhost:11434",
        timeout=120,
        max_output_tokens=300,
        num_ctx=4096,
    )


def test_the_local_model_is_built_with_our_limits_and_needs_no_key():
    model = ollama_provider()()  # constructing it does not contact the server
    assert model.model == "qwen2.5:3b"
    assert model.base_url == "http://localhost:11434"
    assert model.temperature == 0
    assert model.num_predict == 300  # the cap on one answer
    assert model.num_ctx == 4096


def test_the_local_model_is_created_once_and_reused():
    p = ollama_provider()
    assert p() is p()


def test_the_local_provider_explains_how_to_fix_an_outage():
    message = ollama_provider().unavailable_message
    assert "Ollama" in message and "qwen2.5:3b" in message


# ---------- Groq: fast hosted models behind an OpenAI-compatible API ----------

GROQ_URL = "https://api.groq.com/openai/v1"


def groq_provider(key="test-key"):
    return GroqModelProvider(
        api_key=key,
        model="llama-x",
        timeout=7,
        max_output_tokens=200,
        base_url=GROQ_URL,
    )


def test_the_groq_model_uses_groqs_address_and_our_limits():
    model = groq_provider()()  # constructing it makes no network call
    assert model.model_name == "llama-x"
    assert model.openai_api_base == GROQ_URL  # NOT api.openai.com
    assert model.temperature == 0
    assert model.max_retries == 2
    assert model.request_timeout == 7
    assert model.max_tokens == 200


def test_a_missing_groq_key_names_the_groq_setting_not_openais():
    with pytest.raises(ServiceUnavailable) as exc:
        groq_provider(key="")()
    assert "GROQ_API_KEY" in exc.value.message
    assert "OPENAI_API_KEY" not in exc.value.message


def test_the_groq_outage_message_mentions_the_key_and_the_rate_limit():
    message = groq_provider().unavailable_message
    assert "GROQ_API_KEY" in message and "rate limit" in message


def test_plain_openai_still_uses_the_default_address():
    assert provider()().openai_api_base is None  # unchanged behaviour


def test_the_groq_settings_are_wired_through(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GROQ_MODEL", "some-model")
    get_settings.cache_clear()
    try:
        model = build_model_provider()()
        assert model.model_name == "some-model"
        assert model.openai_api_base == GROQ_URL
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "setting,expected",
    [
        ("ollama", OllamaModelProvider),
        ("openai", OpenAIModelProvider),
        ("groq", GroqModelProvider),
    ],
)
def test_the_ai_is_chosen_by_the_llm_provider_setting(monkeypatch, setting, expected):
    monkeypatch.setenv("LLM_PROVIDER", setting)
    get_settings.cache_clear()
    try:
        assert isinstance(build_model_provider(), expected)
    finally:
        get_settings.cache_clear()


def test_an_unknown_provider_name_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "skynet")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError):
            get_settings()
    finally:
        get_settings.cache_clear()
