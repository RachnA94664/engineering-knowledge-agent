"""LangSmith tracing: optional, off by default, and never allowed to break or slow a request.

What it gives you: a dashboard of every chat message: the router's decision, each tool call
with its arguments, the prompts sent to the AI, timings and errors.

Design (and why):
  * OFF unless LANGSMITH_TRACING=true AND a real key is set (a placeholder does not count).
  * WE build the tracer and hand it to each run (see `AgentRuntime`), instead of switching
    LangSmith on through environment variables. That way:
      - the timeouts and the retry limit are ours (a dead LangSmith cannot make a request or
        a shutdown hang; the library has no environment setting for this),
      - the privacy switch is a plain argument,
      - the API key is never copied into the process environment, and
      - nothing is cached per process, so it behaves the same in tests and in production.
  * `configure_tracing` also forces every implicit tracing switch OFF, so an environment
    variable set somewhere else can never turn on a second, uncontrolled stream of traces.
  * Everything here is wrapped so a tracing problem can never reach the user.
"""

import logging
import os

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.tracing")

PLACEHOLDER_PREFIX = "your-"  # the value shipped in .env.example

# How long we wait on LangSmith. Short on purpose: tracing must never hold anything up.
CONNECT_TIMEOUT_MS = 2_000
READ_TIMEOUT_MS = 5_000

# Every switch LangSmith / LangChain might read on its own.
_TRACING_SWITCHES = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING")


def tracing_requested(settings: Settings) -> bool:
    """True only if tracing is switched on AND a real (non-placeholder) key is present."""
    key = settings.langsmith_api_key.strip()
    return settings.langsmith_tracing and bool(key) and not key.startswith(PLACEHOLDER_PREFIX)


def configure_tracing(settings: Settings | None = None) -> bool:
    """Force every IMPLICIT tracing switch off. Returns True if our own tracer will be used.

    Traces are only ever produced by the tracer from `build_tracer`, never by environment
    variables, so what is sent is always exactly what the settings allow.
    """
    settings = settings or get_settings()
    for name in _TRACING_SWITCHES:
        os.environ[name] = "false"
    requested = tracing_requested(settings)
    if settings.langsmith_tracing and not requested:
        logger.warning(
            "LANGSMITH_TRACING is true but no real LANGSMITH_API_KEY is set: tracing stays off"
        )
    return requested


def build_tracer(settings: Settings | None = None):
    """Create the LangSmith tracer, or None when tracing is off. Never raises."""
    settings = settings or get_settings()
    if not tracing_requested(settings):
        return None
    try:
        from langchain_core.tracers.langchain import LangChainTracer
        from langsmith import Client
        from urllib3.util.retry import Retry

        hide = True if settings.langsmith_hide_data else None  # True = send no text at all
        client = Client(
            api_url=settings.langsmith_endpoint or None,  # None = the LangSmith cloud
            api_key=settings.langsmith_api_key.strip(),
            timeout_ms=(CONNECT_TIMEOUT_MS, READ_TIMEOUT_MS),
            retry_config=Retry(total=1, backoff_factor=0),  # one quick retry, then give up
            hide_inputs=hide,
            hide_outputs=hide,
        )
        tracer = LangChainTracer(client=client, project_name=settings.langsmith_project)
    except Exception:  # a tracing problem must never stop the app from starting
        logger.exception("could not set up LangSmith tracing: continuing without it")
        return None
    logger.info(
        "LangSmith tracing is ON (project %r, text %s)",
        settings.langsmith_project,
        "hidden" if settings.langsmith_hide_data else "included",
    )
    return tracer


def tag_current_run(config: dict | None, tags: list[str], metadata: dict[str, str]) -> None:
    """Add tags and metadata to the ROOT trace run of this chat message (best effort).

    Lets you filter the dashboard, for example by intent. Does nothing when tracing is off.

    How: inside a graph node, LangSmith's "current run" is only the node's own run, with no
    link to the root. But the tracer object in the node's callbacks tracks every active run,
    including the root, so we tag through it before the run is sent.
    """
    try:
        callbacks = (config or {}).get("callbacks")
        for handler in getattr(callbacks, "handlers", None) or []:
            for run in (getattr(handler, "run_map", None) or {}).values():
                if run.parent_run_id is None:  # the root run ("chat")
                    run.tags = sorted(set(run.tags or []) | set(tags))
                    extra = dict(run.extra or {})
                    extra["metadata"] = {**extra.get("metadata", {}), **metadata}
                    run.extra = extra
    except Exception:  # tracing must never be able to break a request
        logger.debug("could not tag the trace run", exc_info=True)
