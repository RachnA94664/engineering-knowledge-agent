"""All SQL about test cases lives here."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TestCase


def for_requirement(session: Session, requirement_id: str) -> list[TestCase]:
    return list(
        session.scalars(
            select(TestCase).where(TestCase.requirement_id == requirement_id).order_by(TestCase.id)
        )
    )


def set_status(session: Session, test_ids: Iterable[str], status: str) -> None:
    """Change the status of some test cases. Part of the CALLER's transaction."""
    for test in session.scalars(select(TestCase).where(TestCase.id.in_(list(test_ids)))):
        test.status = status
