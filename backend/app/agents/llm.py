"""The ONLY place that creates the AI chat model.

The rest of the agent code receives a *factory* (a function that returns a LangChain
chat model). That gives us:
  * tests that use a scripted fake model (no key, no network, no cost)
  * the freedom to change provider by changing this one file
  * a model that is created lazily, so rule-based paths (like refusing a delete request)
    keep working even when no API key is configured
"""

from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.domain.errors import ServiceUnavailable

# A function that returns the chat model to use.
ModelFactory = Callable[[], BaseChatModel]


class OpenAIModelProvider:
    """Builds `ChatOpenAI` on first use, with our cost and safety limits."""

    def __init__(self, api_key: str, model: str, timeout: float, max_output_tokens: int):
        self._api_key = api_key
        self._model_name = model
        self._timeout = timeout
        self._max_output_tokens = max_output_tokens
        self._use_temperature = True
        self._model: ChatOpenAI | None = None

    def __call__(self) -> BaseChatModel:
        if not self._api_key:
            raise ServiceUnavailable("the AI service is not configured (OPENAI_API_KEY is empty)")
        if self._model is None:
            kwargs: dict = {
                "model": self._model_name,
                "api_key": self._api_key,
                "timeout": self._timeout,  # give up on a slow call
                "max_retries": 2,  # retries rate limits / server errors with backoff
                "max_completion_tokens": self._max_output_tokens,  # cap the answer length
            }
            if self._use_temperature:
                kwargs["temperature"] = 0  # as repeatable as the model allows
            self._model = ChatOpenAI(**kwargs)
        return self._model

    def drop_temperature(self) -> bool:
        """Some models reject `temperature`. Stop sending it. True if a retry makes sense."""
        if not self._use_temperature:
            return False
        self._use_temperature = False
        self._model = None
        return True


def build_model_provider() -> OpenAIModelProvider:
    s = get_settings()
    return OpenAIModelProvider(
        api_key=s.openai_api_key,
        model=s.openai_model,
        timeout=s.openai_timeout_seconds,
        max_output_tokens=s.llm_max_output_tokens,
    )
