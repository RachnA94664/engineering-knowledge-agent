"""Endpoints for changing data. Nothing is edited directly.

The only way to change a record is to propose, then confirm::

    POST /changes              propose (saved as pending, NOT applied)
    POST /changes/{id}/confirm apply it
    POST /changes/{id}/reject  discard it

There is deliberately no PUT, PATCH or DELETE on any record.
"""

from fastapi import APIRouter

from app.api.deps import API_SOURCE, ERRORS, SessionDep
from app.api.schemas import (
    ActorIn,
    ChangeOut,
    ConfirmOut,
    ProposeChangeIn,
    ProposeOut,
    RejectOut,
    RiskOut,
)
from app.services import changes, reviews

router = APIRouter(tags=["changes"])


@router.get("/changes", response_model=list[ChangeOut])
def list_pending(session: SessionDep):
    """List the changes waiting to be confirmed or rejected.

    \f
    Args:
        session: The database session.

    Returns:
        The pending changes, oldest first.
    """
    return changes.list_pending_changes(session)


@router.post(
    "/changes",
    response_model=ProposeOut,
    status_code=201,
    responses={404: ERRORS[404], 409: ERRORS[409], 422: ERRORS[422]},
)
def propose_change(body: ProposeChangeIn, session: SessionDep):
    """Propose a change to a requirement. Returns the pending change and a preview.

    \f
    Args:
        body: The requirement, the fields to change and who proposes it.
        session: The database session.

    Returns:
        The saved pending change and a preview of old and new values.
    """
    return changes.propose_requirement_change(
        session,
        body.requirement_id,
        body.patch,
        proposed_by=body.proposed_by,
        source=API_SOURCE,
    )


@router.post(
    "/changes/{change_id}/confirm",
    response_model=ConfirmOut,
    responses={404: ERRORS[404], 409: ERRORS[409], 422: ERRORS[422]},
)
def confirm_change(change_id: int, body: ActorIn, session: SessionDep):
    """Apply a pending change. Confirming twice is harmless (already_applied=true).

    \f
    Args:
        change_id: The ID of the pending change.
        body: Who is confirming it.
        session: The database session.

    Returns:
        The applied change, the updated requirement and the automatic impact report.
    """
    return changes.confirm_change(session, change_id, actor=body.actor, source=API_SOURCE)


@router.post(
    "/changes/{change_id}/reject",
    response_model=RejectOut,
    responses={404: ERRORS[404], 409: ERRORS[409], 422: ERRORS[422]},
)
def reject_change(change_id: int, body: ActorIn, session: SessionDep):
    """Discard a pending change without applying it.

    \f
    Args:
        change_id: The ID of the pending change.
        body: Who is rejecting it.
        session: The database session.

    Returns:
        The rejected change.
    """
    return changes.reject_change(session, change_id, actor=body.actor, source=API_SOURCE)


@router.post(
    "/risks/{risk_id}/reviewed",
    response_model=RiskOut,
    tags=["risks"],
    responses={404: ERRORS[404], 422: ERRORS[422]},
)
def risk_reviewed(risk_id: str, body: ActorIn, session: SessionDep):
    """A person confirms they reviewed a flagged risk. Clears `needs_review`; safe to repeat.

    \f
    Args:
        risk_id: The risk's ID, for example RISK-003.
        body: Who reviewed it.
        session: The database session.

    Returns:
        The risk, with its review flag cleared.
    """
    return reviews.mark_risk_reviewed(session, risk_id, actor=body.actor, source=API_SOURCE)
