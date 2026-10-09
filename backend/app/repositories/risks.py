"""All SQL about risk items lives here."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RequirementRisk, RiskItem


def get(session: Session, risk_id: str) -> RiskItem | None:
    """Get a risk item by its ID.

    Args:
        session: The database session.
        risk_id: The ID of the risk, for example ``RISK-001``.

    Returns:
        The risk, or None if there is no such risk.
    """
    return session.get(RiskItem, risk_id)


def list_all(session: Session) -> list[RiskItem]:
    """List every risk item, ordered by ID.

    Score and level are derived in the domain layer, so filtering by level happens in the
    service, not in SQL.

    Args:
        session: The database session.

    Returns:
        All risk items.
    """
    return list(session.scalars(select(RiskItem).order_by(RiskItem.id)))


def for_requirement(session: Session, requirement_id: str) -> list[RiskItem]:
    """List the risks linked to a requirement (through the ``requirement_risks`` table).

    Args:
        session: The database session.
        requirement_id: The ID of the requirement.

    Returns:
        The linked risks ordered by ID; empty if there are none.
    """
    return list(
        session.scalars(
            select(RiskItem)
            .join(RequirementRisk, RequirementRisk.risk_id == RiskItem.id)
            .where(RequirementRisk.requirement_id == requirement_id)
            .order_by(RiskItem.id)
        )
    )


def set_needs_review(session: Session, risk_ids: Iterable[str], flag: bool) -> None:
    """Set or clear the review flag. Part of the CALLER's transaction (nothing is committed).

    Args:
        session: The database session.
        risk_ids: The risks to change.
        flag: True to flag them for review, False to clear the flag.
    """
    for risk in session.scalars(select(RiskItem).where(RiskItem.id.in_(list(risk_ids)))):
        risk.needs_review = flag
