"""Application settings, read from environment variables (and a local .env file).

Configuration is not code: the same code runs on your laptop and on Render with
different values. Never hard-code keys or URLs here.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which AI to use: OpenAI (a paid API) or Ollama (a free model running on your own PC).
    llm_provider: Literal["openai", "ollama"] = "openai"
    llm_max_output_tokens: int = 800  # cap on the length of any one AI answer

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0  # give up on a slow AI call

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout_seconds: float = 300.0  # a local model on a CPU can be slow
    ollama_num_ctx: int = 8192  # how much text the local model can read at once
    database_url: str = "sqlite:///./knowledge.db"
    allowed_origins: str = "http://localhost:5173"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Create the settings once and reuse them."""
    return Settings()
