"""Shared FastAPI dependencies."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents.llm import build_model_provider
from app.agents.runtime import AgentRuntime
from app.core.tracing import build_tracer
from app.db.session import get_session

# One database session per request (opened before, closed after).
# Tests replace `get_session` with a session on a temporary database.
SessionDep = Annotated[Session, Depends(get_session)]


@lru_cache
def _runtime() -> AgentRuntime:
    """Build the agent runtime once per process.

    The graph (and the system prompts) are built here; the AI model itself is created lazily.
    The tracer is None unless LangSmith tracing is switched on in the settings.

    Returns:
        The shared runtime.
    """
    return AgentRuntime(build_model_provider(), tracer=build_tracer())


def get_runtime() -> AgentRuntime:
    """Provide the agent runtime to a route. Tests replace this with a scripted fake model.

    Returns:
        The shared runtime.
    """
    return _runtime()


RuntimeDep = Annotated[AgentRuntime, Depends(get_runtime)]

# Requests that arrive over HTTP always come from the UI. A client cannot claim
# to be an "agent" or "system": the audit log source is set here, on the server.
API_SOURCE = "ui"

# Error responses shown in the /docs page.
ERRORS = {
    404: {"description": "Not found"},
    409: {"description": "Conflict with the current state"},
    422: {"description": "Invalid input"},
    503: {"description": "The AI service is not available"},
}
