"""All SQL about impact reports lives here."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ImpactReport


def add(
    session: Session, *, requirement_id: str, change_id: int, level: str, report: dict
) -> ImpactReport:
    """Store a report in the CALLER's transaction. One report per change (a UNIQUE column).

    Args:
        session: The database session.
        requirement_id: The requirement the change was applied to.
        change_id: The applied change this report describes.
        level: The impact level: ``low``, ``medium`` or ``high``.
        report: The full report (stored as JSON text).

    Returns:
        The new row, with its ``id`` assigned (nothing is committed yet).
    """
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
    """Get the report of one applied change.

    Args:
        session: The database session.
        change_id: The ID of the applied change.

    Returns:
        The report, or None if that change has none.
    """
    return session.scalars(select(ImpactReport).where(ImpactReport.change_id == change_id)).first()


def latest_for_requirement(session: Session, requirement_id: str) -> ImpactReport | None:
    """Get the most recent report for a requirement.

    Args:
        session: The database session.
        requirement_id: The ID of the requirement.

    Returns:
        The newest report, or None if no change to it has been confirmed yet.
    """
    return session.scalars(
        select(ImpactReport)
        .where(ImpactReport.requirement_id == requirement_id)
        .order_by(ImpactReport.id.desc())
    ).first()
