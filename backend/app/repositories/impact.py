"""All SQL about impact reports lives here."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ImpactReport


def add(
    session: Session, *, requirement_id: str, change_id: int, level: str, report: dict
) -> ImpactReport:
    """Store a report in the CALLER's transaction. One report per change (a UNIQUE column)."""
    row = ImpactReport(
        requirement_id=requirement_id,
        change_id=change_id,
        level=level,
        report=json.dumps(report, sort_keys=True),
    )
    session.add(row)
    session.flush()  # assigns row.id without committing
    return row


def get_for_change(session: Session, change_id: int) -> ImpactReport | None:
    return session.scalars(select(ImpactReport).where(ImpactReport.change_id == change_id)).first()


def latest_for_requirement(session: Session, requirement_id: str) -> ImpactReport | None:
    return session.scalars(
        select(ImpactReport)
        .where(ImpactReport.requirement_id == requirement_id)
        .order_by(ImpactReport.id.desc())
    ).first()
