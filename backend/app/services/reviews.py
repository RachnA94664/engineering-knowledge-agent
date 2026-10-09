"""A person marks a flagged risk as reviewed (this clears the "needs review" flag)."""

from sqlalchemy.orm import Session

from app.domain.errors import NotFound
from app.domain.ids import ensure_valid_id
from app.repositories import audit as audit_repo
from app.repositories import risks as risk_repo
from app.services.checks import check_who
from app.services.serializers import risk_to_dict
from app.services.uow import unit_of_work


def mark_risk_reviewed(session: Session, risk_id: str, *, actor: str, source: str = "ui") -> dict:
    """Clear a risk's review flag. Safe to repeat: an already-reviewed risk changes nothing.

    Args:
        session: The database session.
        risk_id: The ID of the risk, for example ``RISK-003``.
        actor: The person who reviewed it (written to the audit log).
        source: Where it came from: ``ui``, ``agent`` or ``system``.

    Returns:
        The risk as a dictionary, with its score and level.

    Raises:
        NotFound: If the risk does not exist.
        ValidationError: If the ID or the actor is invalid (raised by the checks called).
    """
    ensure_valid_id("risk", risk_id)
    check_who(actor, source)
    risk = risk_repo.get(session, risk_id)
    if risk is None:
        raise NotFound(f"risk {risk_id} does not exist")

    if risk.needs_review:
        with unit_of_work(session):
            risk_repo.set_needs_review(session, [risk_id], False)
            audit_repo.add_entry(
                session,
                actor=actor,
                source=source,
                entity_type="risk",
                entity_id=risk_id,
                action="review",
                old={"needs_review": True},
                new={"needs_review": False},
            )
    return risk_to_dict(risk)
