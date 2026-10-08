"""Load the agents' system prompts, from LangSmith Prompt Hub when it is configured.

Where a prompt comes from is chosen by ``PROMPT_SOURCE``:

* ``langsmith`` (the default): pull ``<PROMPT_NAME_PREFIX><name>`` (for example
  ``eka-query``) from LangSmith Prompt Hub, optionally pinned to ``PROMPT_TAG``. This needs a
  real ``LANGSMITH_API_KEY``. If anything goes wrong (no key, no network, the prompt is
  missing, the prompt has the wrong shape) a warning is logged and the local file is used
  instead, so LangSmith can never take the app down.
* ``local``: always use the files in ``prompts/``. The tests use this, so they need neither
  a network nor a key.

The files in ``prompts/`` stay in the repository as the reviewed baseline and the fallback.
The safety rules (each agent's tool allow-list, the grounding check, the refusals, the
limits) are code and not prompt text, so a prompt edited in LangSmith can change how the AI
words its answers but cannot give it new powers.

Prompts are loaded once per process (the first time they are needed) and then cached, so
after editing a prompt in LangSmith, restart the backend. Check what is in use with::

    python -m app.agents.prompt_loader
"""

import logging
from functools import lru_cache
from pathlib import Path

from langsmith.utils import LangSmithConnectionError

from app.core.config import Settings, get_settings
from app.core.tracing import CONNECT_TIMEOUT_MS, PLACEHOLDER_PREFIX, READ_TIMEOUT_MS

logger = logging.getLogger("app.prompts")

PROMPT_DIR = Path(__file__).parent / "prompts"
PROMPT_NAMES = ("query", "update", "analysis", "router")
MAX_PROMPT_CHARS = 20_000  # a system prompt is a page of rules, not a book

# name -> "langsmith" or "local": where each prompt actually came from (for logs and checks).
_origins: dict[str, str] = {}

# Failures that mean "LangSmith cannot be reached at all" (as opposed to "this one prompt is
# missing"). After one of these we stop asking, so an outage costs one timeout, not four.
_NETWORK_ERRORS = (LangSmithConnectionError, ConnectionError, TimeoutError)
_unreachable = False


class PromptError(Exception):
    """A prompt pulled from LangSmith cannot be used (the reason is in the message)."""


def local_prompt(name: str) -> str:
    """Read a prompt from the ``prompts/`` folder.

    Args:
        name: The prompt name, for example ``"query"``.

    Returns:
        The prompt text without surrounding whitespace.
    """
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def has_real_key(settings: Settings) -> bool:
    """Tell whether a usable LangSmith API key is configured.

    Args:
        settings: The application settings.

    Returns:
        True if a key is set and it is not the placeholder shipped in ``.env.example``.
    """
    key = settings.langsmith_api_key.strip()
    return bool(key) and not key.startswith(PLACEHOLDER_PREFIX)


def langsmith_prompt_name(settings: Settings, name: str) -> str:
    """Build the identifier of a prompt in Prompt Hub.

    Args:
        settings: The application settings (prefix and optional tag).
        name: The prompt name, for example ``"query"``.

    Returns:
        ``eka-query`` or, when a tag is configured, ``eka-query:production``.
    """
    base = f"{settings.prompt_name_prefix}{name}"
    tag = settings.prompt_tag.strip()
    return f"{base}:{tag}" if tag else base


def _make_client(settings: Settings):
    """Create a LangSmith client with short timeouts.

    A slow or dead LangSmith must not be able to hang start-up, so the timeouts are ours and
    there is a single quick retry. Tests replace this function with a fake.

    Args:
        settings: The application settings (key and optional endpoint).

    Returns:
        A ``langsmith.Client``.
    """
    from langsmith import Client
    from urllib3.util.retry import Retry

    return Client(
        api_url=settings.langsmith_endpoint or None,  # None = the LangSmith cloud
        api_key=settings.langsmith_api_key.strip(),
        timeout_ms=(CONNECT_TIMEOUT_MS, READ_TIMEOUT_MS),
        retry_config=Retry(total=1, backoff_factor=0),
    )


def system_text(prompt) -> str:
    """Extract the text of a prompt pulled from LangSmith, if it is a plain system prompt.

    We only accept what we know how to use: system messages, no template variables, not empty
    and not huge. Anything else is rejected so the caller falls back to the local file.

    Args:
        prompt: The object returned by ``Client.pull_prompt`` (a chat prompt template).

    Returns:
        The system text.

    Raises:
        PromptError: If the prompt has template variables, contains non-system messages, is
            empty, or is longer than ``MAX_PROMPT_CHARS``.
    """
    variables = sorted(getattr(prompt, "input_variables", None) or [])
    if variables:
        raise PromptError(
            f"it has template variables {variables}; our prompts must have none "
            "(write {{ and }} for a literal brace)"
        )
    messages = prompt.invoke({}).to_messages()
    if not messages:
        raise PromptError("it has no messages")
    others = sorted({m.type for m in messages if m.type != "system"})
    if others:
        raise PromptError(f"it contains {others} messages; keep only the System message")
    text = "\n\n".join(str(m.content) for m in messages).strip()
    if not text:
        raise PromptError("it is empty")
    if len(text) > MAX_PROMPT_CHARS:
        raise PromptError(f"it is {len(text)} characters long (the limit is {MAX_PROMPT_CHARS})")
    return text


def pull_prompt_text(settings: Settings, name: str) -> str:
    """Pull one prompt from LangSmith Prompt Hub and return its system text.

    Args:
        settings: The application settings.
        name: The prompt name, for example ``"query"``.

    Returns:
        The system text of the prompt.

    Raises:
        PromptError: If the pulled prompt cannot be used (see ``system_text``).
        Exception: Whatever the LangSmith client raises (network, authentication, not found).
    """
    client = _make_client(settings)
    return system_text(client.pull_prompt(langsmith_prompt_name(settings, name)))


def _redact(message: str, settings: Settings) -> str:
    """Make an error message safe to log: no API key, and not too long."""
    key = settings.langsmith_api_key.strip()
    if key:
        message = message.replace(key, "<hidden>")
    return message[:200]


@lru_cache
def load_prompt(name: str) -> str:
    """Return the system prompt for an agent (cached for the life of the process).

    Args:
        name: The prompt name: ``query``, ``update``, ``analysis`` or ``router``.

    Returns:
        The prompt text, from LangSmith when configured and reachable, else from the file.
    """
    global _unreachable
    settings = get_settings()
    if settings.prompt_source == "langsmith":
        remote = langsmith_prompt_name(settings, name)
        if not has_real_key(settings):
            logger.info("no real LANGSMITH_API_KEY: prompt %r comes from the local file", name)
        elif _unreachable:
            logger.info("LangSmith was unreachable earlier: prompt %r comes from the file", name)
        else:
            try:
                text = pull_prompt_text(settings, name)
            except Exception as exc:  # LangSmith problems must never stop the app
                if isinstance(exc, _NETWORK_ERRORS):
                    _unreachable = True  # do not wait for the same timeout again
                logger.warning(
                    "could not load prompt %r from LangSmith (%s: %s): using the local file",
                    remote,
                    type(exc).__name__,
                    _redact(str(exc), settings),
                )
            else:
                _origins[name] = "langsmith"
                logger.info("prompt %r loaded from LangSmith as %r", name, remote)
                return text
    _origins[name] = "local"
    return local_prompt(name)


def prompt_origin(name: str) -> str:
    """Tell where a prompt came from.

    Args:
        name: The prompt name.

    Returns:
        ``"langsmith"``, ``"local"``, or ``"not loaded yet"``.
    """
    return _origins.get(name, "not loaded yet")


def main() -> None:
    """Print where each prompt would come from, never the prompt text itself."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    print(f"PROMPT_SOURCE={settings.prompt_source}  tag={settings.prompt_tag or '(latest)'}")
    for name in PROMPT_NAMES:
        text = load_prompt(name)
        print(f"  {name:9} from {prompt_origin(name):9} ({len(text)} characters)")


if __name__ == "__main__":
    main()
