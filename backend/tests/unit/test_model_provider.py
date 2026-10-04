"""The OpenAI model provider, tested WITHOUT any network (no call is ever made)."""

import pytest

from app.agents.llm import OpenAIModelProvider
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
