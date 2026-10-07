"""The ONLY place that creates the AI chat model.

The rest of the agent code receives a *factory* (a function that returns a LangChain
chat model). That gives us:
  * tests that use a scripted fake model (no key, no network, no cost)
  * the freedom to choose the AI by a setting: OpenAI (paid API), Groq (fast hosted API with
    a free tier) or Ollama (a free model running on your own PC), without touching the agents
  * a model that is created lazily, so rule-based paths (like refusing a delete request)
    keep working even when no AI is configured or reachable
"""

from collections.abc import Callable

import httpx
import ollama
import openai
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.domain.errors import ServiceUnavailable

# A function that returns the chat model to use.
ModelFactory = Callable[[], BaseChatModel]

# Everything that can go wrong when talking to an AI provider (network, rate limit, billing,
# an unknown model, a stopped local server). The runtime turns all of these into one safe
# "service unavailable" answer and never shows the original message.
PROVIDER_ERRORS: tuple[type[BaseException], ...] = (
    openai.OpenAIError,
    ollama.ResponseError,
    ollama.RequestError,
    httpx.HTTPError,
    ConnectionError,  # the Ollama client raises this when the server is not running
)

DEFAULT_UNAVAILABLE_MESSAGE = "the AI service is not available right now"


class OpenAIModelProvider:
    """Builds `ChatOpenAI` on first use, with our cost and safety limits.

    Any service that speaks the OpenAI protocol can reuse this class: set `base_url` and
    `key_name` (the setting named in the "not configured" message). See `GroqModelProvider`.
    """

    unavailable_message = DEFAULT_UNAVAILABLE_MESSAGE
    key_name = "OPENAI_API_KEY"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float,
        max_output_tokens: int,
        base_url: str | None = None,
    ):
        self._api_key = api_key
        self._model_name = model
        self._timeout = timeout
        self._max_output_tokens = max_output_tokens
        self._base_url = base_url
        self._use_temperature = True
        self._model: ChatOpenAI | None = None

    def __call__(self) -> BaseChatModel:
        if not self._api_key:
            raise ServiceUnavailable(f"the AI service is not configured ({self.key_name} is empty)")
        if self._model is None:
            kwargs: dict = {
                "model": self._model_name,
                "api_key": self._api_key,
                "timeout": self._timeout,  # give up on a slow call
                "max_retries": 2,  # retries rate limits / server errors with backoff
                "max_completion_tokens": self._max_output_tokens,  # cap the answer length
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url  # e.g. Groq's OpenAI-compatible address
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


class GroqModelProvider(OpenAIModelProvider):
    """Groq: fast hosted open models behind an OpenAI-compatible API (free tier available).

    The free tier has rate limits (requests and tokens per minute and per day), so a busy
    moment can fail with a "rate limit" error; our runtime turns that into the message below.
    """

    key_name = "GROQ_API_KEY"
    unavailable_message = (
        "the Groq AI service did not answer. The key may be wrong or missing (GROQ_API_KEY), "
        "or the free-tier rate limit was reached: wait a minute and try again."
    )


class OllamaModelProvider:
    """Builds `ChatOllama` (a model running locally under Ollama) on first use.

    No API key and no cost. The trade-offs: it needs Ollama running, a downloaded model, and
    on a CPU it is slow, so the timeout is long. Small models are also less reliable at
    calling tools; our safety checks still apply to whatever they produce.
    """

    def __init__(
        self, model: str, base_url: str, timeout: float, max_output_tokens: int, num_ctx: int
    ):
        self._model_name = model
        self._base_url = base_url
        self._timeout = timeout
        self._max_output_tokens = max_output_tokens
        self._num_ctx = num_ctx
        self._model: ChatOllama | None = None

    @property
    def unavailable_message(self) -> str:
        return (
            f"the local AI (Ollama, model '{self._model_name}') is not reachable. "
            "Is Ollama running and the model downloaded?"
        )

    def __call__(self) -> BaseChatModel:
        if self._model is None:
            self._model = ChatOllama(
                model=self._model_name,
                base_url=self._base_url,
                temperature=0,
                num_predict=self._max_output_tokens,  # cap the answer length
                num_ctx=self._num_ctx,  # how much text the model can read at once
                client_kwargs={"timeout": self._timeout},  # give up on a stuck call
            )
        return self._model


def build_model_provider() -> OpenAIModelProvider | OllamaModelProvider:
    """Choose the AI from the LLM_PROVIDER setting."""
    s = get_settings()
    if s.llm_provider == "groq":
        return GroqModelProvider(
            api_key=s.groq_api_key,
            model=s.groq_model,
            timeout=s.groq_timeout_seconds,
            max_output_tokens=s.llm_max_output_tokens,
            base_url=s.groq_base_url,
        )
    if s.llm_provider == "ollama":
        return OllamaModelProvider(
            model=s.ollama_model,
            base_url=s.ollama_base_url,
            timeout=s.ollama_timeout_seconds,
            max_output_tokens=s.llm_max_output_tokens,
            num_ctx=s.ollama_num_ctx,
        )
    return OpenAIModelProvider(
        api_key=s.openai_api_key,
        model=s.openai_model,
        timeout=s.openai_timeout_seconds,
        max_output_tokens=s.llm_max_output_tokens,
    )
