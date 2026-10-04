"""All SQL about risk items lives here."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RequirementRisk, RiskItem


def get(session: Session, risk_id: str) -> RiskItem | None:
    return session.get(RiskItem, risk_id)


def list_all(session: Session) -> list[RiskItem]:
    # Score and level are derived in the domain layer, so filtering by level
    # happens in the service, not in SQL.
    return list(session.scalars(select(RiskItem).order_by(RiskItem.id)))


def for_requirement(session: Session, requirement_id: str) -> list[RiskItem]:
    """The risks linked to a requirement (through the requirement_risks table)."""
    return list(
        session.scalars(
            select(RiskItem)
            .join(RequirementRisk, RequirementRisk.risk_id == RiskItem.id)
            .where(RequirementRisk.requirement_id == requirement_id)
            .order_by(RiskItem.id)
        )
    )


def set_needs_review(session: Session, risk_ids: Iterable[str], flag: bool) -> None:
    """Set or clear the review flag. Part of the CALLER's transaction (nothing is committed)."""
    for risk in session.scalars(select(RiskItem).where(RiskItem.id.in_(list(risk_ids)))):
        risk.needs_review = flag
