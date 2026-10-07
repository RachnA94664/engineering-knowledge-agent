"""Application settings, read from environment variables (and a local .env file).

Configuration is not code: the same code runs on your laptop and on Render with
different values. Never hard-code keys or URLs here.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which AI to use: OpenAI (a paid API), Groq (a fast hosted API with a free tier) or
    # Ollama (a free model running on your own PC).
    llm_provider: Literal["openai", "ollama", "groq"] = "openai"
    llm_max_output_tokens: int = 800  # cap on the length of any one AI answer

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0  # give up on a slow AI call

    # Groq speaks the same protocol as OpenAI, so only the address, key and model differ.
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = 30.0

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout_seconds: float = 300.0  # a local model on a CPU can be slow
    ollama_num_ctx: int = 8192  # how much text the local model can read at once

    # LangSmith tracing (optional). OFF unless the flag is true AND a real key is set.
    # Traces contain the text of questions and records, so only use dummy data, or turn on
    # LANGSMITH_HIDE_DATA to send only the structure and timings.
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "engineering-knowledge-agent"
    langsmith_endpoint: str = ""  # empty = the LangSmith cloud default
    langsmith_hide_data: bool = False  # trace only structure and timings, not the text

    database_url: str = "sqlite:///./knowledge.db"
    allowed_origins: str = "http://localhost:5173"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Create the settings once and reuse them."""
    return Settings()
