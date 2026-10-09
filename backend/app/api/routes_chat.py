"""POST /chat: ask a question or request a change in plain English."""

from dataclasses import asdict

from fastapi import APIRouter

from app.api.deps import ERRORS, RuntimeDep, SessionDep
from app.api.schemas import ChatIn, ChatOut

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatOut,
    responses={422: ERRORS[422], 503: ERRORS[503]},
)
def chat(body: ChatIn, session: SessionDep, runtime: RuntimeDep):
    """Ask in plain English. Answers come only from the database; changes are proposals.

    \f
    Args:
        body: The user's message.
        session: The database session the agents' tools will use.
        runtime: The agent runtime.

    Returns:
        The answer, the records and tool trace behind it, and any proposals.
    """
    return asdict(runtime.run(session, body.message))
