"""All SQL about test cases lives here."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TestCase


def for_requirement(session: Session, requirement_id: str) -> list[TestCase]:
    """List the test cases that belong to a requirement.

    Args:
        session: The database session.
        requirement_id: The ID of the requirement.

    Returns:
        Its test cases ordered by ID; empty if it has none.
    """
    return list(
        session.scalars(
            select(TestCase).where(TestCase.requirement_id == requirement_id).order_by(TestCase.id)
        )
    )


def set_status(session: Session, test_ids: Iterable[str], status: str) -> None:
    """Change the status of some test cases. Part of the CALLER's transaction.

    Args:
        session: The database session.
        test_ids: The test cases to change.
        status: The new status: ``not_run``, ``pass``, ``fail`` or ``blocked``.
    """
    for test in session.scalars(select(TestCase).where(TestCase.id.in_(list(test_ids)))):
        test.status = status
