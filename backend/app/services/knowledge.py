"""Read-only use cases. The API and the agents call these, never the repositories."""

from sqlalchemy.orm import Session

from app.domain.enums import RISK_LEVELS
from app.domain.errors import NotFound, ValidationError
from app.domain.ids import ensure_valid_id
from app.repositories import audit as audit_repo
from app.repositories import impact as impact_repo
from app.repositories import requirements as req_repo
from app.repositories import risks as risk_repo
from app.repositories import testcases as tc_repo
from app.services import serializers as ser


def _require_requirement(session: Session, requirement_id: str):
    """Load a requirement that must exist.

    Args:
        session: The database session.
        requirement_id: The ID of the requirement.

    Returns:
        The requirement row.

    Raises:
        NotFound: If there is no such requirement.
    """
    ensure_valid_id("requirement", requirement_id)
    req = req_repo.get(session, requirement_id)
    if req is None:
        raise NotFound(f"requirement {requirement_id} does not exist")
    return req


def get_requirement(session: Session, requirement_id: str) -> dict:
    """Get one requirement.

    Args:
        session: The database session.
        requirement_id: The ID of the requirement, for example ``REQ-001``.

    Returns:
        The requirement as a dictionary.
    """
    return ser.requirement_to_dict(_require_requirement(session, requirement_id))


def list_requirements(session: Session) -> list[dict]:
    """List every requirement.

    Args:
        session: The database session.

    Returns:
        All requirements as dictionaries, ordered by ID.
    """
    return [ser.requirement_to_dict(r) for r in req_repo.list_all(session)]


def get_test_cases_for_requirement(session: Session, requirement_id: str) -> list[dict]:
    """List the test cases of a requirement.

    Args:
        session: The database session.
        requirement_id: The ID of the requirement.

    Returns:
        Its test cases as dictionaries. An existing requirement with no tests gives an empty
        list; an unknown requirement raises an error (it is never silently an empty list).
    """
    _require_requirement(session, requirement_id)  # unknown requirement is NotFound, not []
    return [ser.testcase_to_dict(t) for t in tc_repo.for_requirement(session, requirement_id)]


def list_requirements_without_tests(session: Session) -> list[dict]:
    """List the requirements that have no test case at all.

    Args:
        session: The database session.

    Returns:
        Those requirements as dictionaries.
    """
    return [ser.requirement_to_dict(r) for r in req_repo.list_without_tests(session)]


def list_risks(
    session: Session, level: str | None = None, needs_review: bool | None = None
) -> list[dict]:
    """List risks, highest score first.

    Args:
        session: The database session.
        level: If given, only risks of this level: ``low``, ``medium`` or ``high``.
        needs_review: If given, only risks that are (True) or are not (False) flagged for
            review by the impact analysis.

    Returns:
        The matching risks as dictionaries, each with its derived score and level.

    Raises:
        ValidationError: If ``level`` is not one of the allowed levels.
    """
    if level is not None and level not in RISK_LEVELS:
        raise ValidationError(f"level must be one of {RISK_LEVELS}, got {level!r}")
    items = [ser.risk_to_dict(r) for r in risk_repo.list_all(session)]
    if level is not None:
        items = [r for r in items if r["level"] == level]
    if needs_review is not None:
        items = [r for r in items if r["needs_review"] is needs_review]
    return sorted(items, key=lambda r: (-r["score"], r["id"]))


def audit_log(session: Session, limit: int = 50, entity_id: str | None = None) -> list[dict]:
    """List the newest audit-log entries.

    Args:
        session: The database session.
        limit: How many entries to return, from 1 to 500.
        entity_id: If given, only entries about this record (for example ``REQ-001``).

    Returns:
        The entries as dictionaries, newest first.

    Raises:
        ValidationError: If ``limit`` is not a whole number from 1 to 500.
    """
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValidationError("limit must be a whole number from 1 to 500")
    return [ser.audit_to_dict(e) for e in audit_repo.list_recent(session, limit, entity_id)]


def get_impact(session: Session, requirement_id: str) -> dict:
    """Get the latest impact report of a requirement.

    A report is created when a change to the requirement is confirmed.

    Args:
        session: The database session.
        requirement_id: The ID of the requirement.

    Returns:
        The report as a dictionary.

    Raises:
        NotFound: If the requirement does not exist, or no change to it has been confirmed
            yet (so there is no report).
    """
    _require_requirement(session, requirement_id)
    row = impact_repo.latest_for_requirement(session, requirement_id)
    if row is None:
        raise NotFound(
            f"no impact report exists for {requirement_id} yet: a confirmed change creates one"
        )
    return ser.impact_to_dict(row)
