"""The automatic impact analysis that runs when a change is confirmed.

It is called from `confirm_change` INSIDE the same transaction, so the change, the test
resets, the risk flags, the report and every audit row are saved together or not at all.

The rules live in `domain/impact.py` (pure). This file only:
  1. reads the requirement's linked test cases and risks,
  2. asks the rules what is affected,
  3. applies those effects, and
  4. records everything (report + audit rows, attributed to the system, not to a person).
"""

from sqlalchemy.orm import Session

from app.domain.impact import analyze
from app.repositories import audit as audit_repo
from app.repositories import impact as impact_repo
from app.repositories import risks as risk_repo
from app.repositories import testcases as tc_repo
from app.services.serializers import impact_to_dict, risk_to_dict

SYSTEM_ACTOR = "impact-analysis"
SYSTEM_SOURCE = "system"


def analyze_and_apply(
    session: Session,
    *,
    requirement_id: str,
    old_values: dict,
    new_values: dict,
    priority_after: str,
    change_id: int,
) -> dict:
    """Analyse a just-applied change, apply its effects and store the report.

    Runs inside the caller's transaction; nothing is committed here.

    Args:
        session: The database session.
        requirement_id: The requirement that was changed.
        old_values: The fields that changed, with their values before the change.
        new_values: The same fields, with their values after the change.
        priority_after: The requirement's priority after the change.
        change_id: The applied change this analysis belongs to.

    Returns:
        The stored impact report, with its row id, change id and creation time.
    """
    tests = [
        {"id": t.id, "title": t.title, "status": t.status}
        for t in tc_repo.for_requirement(session, requirement_id)
    ]
    risks = [risk_to_dict(r) for r in risk_repo.for_requirement(session, requirement_id)]
    changed = {f: {"old": old_values[f], "new": new_values[f]} for f in new_values}

    result = analyze(requirement_id, changed, priority_after, tests, risks)

    def log(entity_type: str, entity_id: str, action: str, old=None, new=None) -> None:
        audit_repo.add_entry(
            session,
            actor=SYSTEM_ACTOR,
            source=SYSTEM_SOURCE,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old=old,
            new=None if new is None else {**new, "caused_by_change": change_id},
        )

    # 1. Passing test cases whose evidence is now out of date go back to "not run".
    for test in result["tests_to_reset"]:
        log("test_case", test["id"], "reset", {"status": test["old_status"]}, {"status": "not_run"})
    tc_repo.set_status(session, [t["id"] for t in result["tests_to_reset"]], "not_run")

    # 2. Risks that may no longer be accurate are flagged for a person to review.
    newly_flagged = [r["id"] for r in result["risks_to_flag"] if not r["already_flagged"]]
    for risk_id in newly_flagged:
        log("risk", risk_id, "flag_review", {"needs_review": False}, {"needs_review": True})
    risk_repo.set_needs_review(session, newly_flagged, True)

    # 3. The report itself, linked to the change that caused it.
    row = impact_repo.add(
        session,
        requirement_id=requirement_id,
        change_id=change_id,
        level=result["level"],
        report=result,
    )
    log("requirement", requirement_id, "impact", new={"report_id": row.id, "level": row.level})
    return impact_to_dict(row)
