"""Read-only endpoints. They only call `services.knowledge`."""

from fastapi import APIRouter

from app.api.deps import ERRORS, SessionDep
from app.api.schemas import AuditOut, ImpactReportOut, RequirementOut, RiskOut, TestCaseOut
from app.services import knowledge

router = APIRouter()


@router.get("/requirements", response_model=list[RequirementOut], tags=["requirements"])
def list_requirements(session: SessionDep):
    """List all requirements.

    \f
    Args:
        session: The database session.

    Returns:
        Every requirement, ordered by ID.
    """
    return knowledge.list_requirements(session)


# NOTE: this route must be declared BEFORE "/requirements/{requirement_id}",
# otherwise "without-tests" would be read as a requirement id.
@router.get(
    "/requirements/without-tests", response_model=list[RequirementOut], tags=["requirements"]
)
def requirements_without_tests(session: SessionDep):
    """List the requirements that have no test cases.

    \f
    Args:
        session: The database session.

    Returns:
        Those requirements.
    """
    return knowledge.list_requirements_without_tests(session)


@router.get(
    "/requirements/{requirement_id}",
    response_model=RequirementOut,
    responses={404: ERRORS[404], 422: ERRORS[422]},
    tags=["requirements"],
)
def get_requirement(requirement_id: str, session: SessionDep):
    """Get one requirement by id, for example REQ-001.

    \f
    Args:
        requirement_id: The requirement's ID.
        session: The database session.

    Returns:
        The requirement. A missing one gives a 404 error.
    """
    return knowledge.get_requirement(session, requirement_id)


@router.get(
    "/requirements/{requirement_id}/test-cases",
    response_model=list[TestCaseOut],
    responses={404: ERRORS[404], 422: ERRORS[422]},
    tags=["requirements"],
)
def test_cases_for_requirement(requirement_id: str, session: SessionDep):
    """List the test cases that belong to a requirement.

    \f
    Args:
        requirement_id: The requirement's ID.
        session: The database session.

    Returns:
        Its test cases (an empty list if it has none).
    """
    return knowledge.get_test_cases_for_requirement(session, requirement_id)


@router.get(
    "/requirements/{requirement_id}/impact",
    response_model=ImpactReportOut,
    responses={404: ERRORS[404], 422: ERRORS[422]},
    tags=["requirements"],
)
def requirement_impact(requirement_id: str, session: SessionDep):
    """Get the latest impact report: what the last confirmed change to this requirement affected.

    \f
    Args:
        requirement_id: The requirement's ID.
        session: The database session.

    Returns:
        The report. A 404 means no change to it has been confirmed yet.
    """
    return knowledge.get_impact(session, requirement_id)


@router.get("/risks", response_model=list[RiskOut], responses={422: ERRORS[422]}, tags=["risks"])
def list_risks(session: SessionDep, level: str | None = None, needs_review: bool | None = None):
    """Risk items, highest score first.

    Filter with ?level=high (low, medium or high) and/or ?needs_review=true to see the risks
    that a confirmed change flagged for review.

    \f
    Args:
        session: The database session.
        level: Only risks of this level.
        needs_review: Only risks that are (true) or are not (false) flagged for review.

    Returns:
        The matching risks, each with its derived score and level.
    """
    return knowledge.list_risks(session, level, needs_review)


@router.get(
    "/audit-log", response_model=list[AuditOut], responses={422: ERRORS[422]}, tags=["audit"]
)
def audit_log(session: SessionDep, limit: int = 50, entity_id: str | None = None):
    """List the most recent audit entries first (1 to 500). Optional ?entity_id=REQ-001.

    \f
    Args:
        session: The database session.
        limit: How many entries to return.
        entity_id: Only entries about this record.

    Returns:
        The audit entries, newest first.
    """
    return knowledge.audit_log(session, limit, entity_id)
