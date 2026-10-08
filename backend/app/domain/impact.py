"""What a confirmed change to a requirement affects. Pure rules: no database, no network.

The rules (all in this one file, so they are easy to read and to change):
  * description edited          -> passing tests are reset to not_run; linked risks flagged
  * priority raised             -> linked risks flagged (tests unchanged)
  * status becomes obsolete     -> linked risks flagged; note that tests may be retired
  * status becomes verified     -> warn if linked tests are not all passing (or there are none)
  * title edited, priority lowered, any other status move -> nothing is affected

Closed risks are never flagged. Impact level:
  * low    nothing is affected
  * high   something is affected AND (the requirement is critical OR its description changed)
  * medium something is affected otherwise
"""

from app.domain.enums import PRIORITIES

_RANK = {priority: rank for rank, priority in enumerate(PRIORITIES)}  # low=0 ... critical=3


def _ids(items: list[dict]) -> str:
    return ", ".join(item["id"] for item in items)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def analyze(
    requirement_id: str,
    changed: dict[str, dict],
    priority_after: str,
    tests: list[dict],
    risks: list[dict],
) -> dict:
    """Work out the impact of one applied change.

    Args:
        requirement_id: The requirement that changed.
        changed: {field: {"old": ..., "new": ...}} for the fields that really changed.
        priority_after: The requirement's priority AFTER the change.
        tests: Its linked test cases: {"id", "title", "status"}.
        risks: Its linked risks: {"id", "title", "score", "level", "status", "needs_review"}.

    Returns:
        The report as a dictionary: ``requirement_id``, ``level`` (low, medium or high),
        ``changed_fields``, ``tests_to_reset``, ``tests_failing``, ``risks_to_flag``,
        ``warnings`` and a one-paragraph ``summary``.
    """
    open_risks = [r for r in risks if r["status"] != "closed"]
    tests_to_reset: list[dict] = []
    risks_to_flag: list[dict] = []
    warnings: list[str] = []

    if "description" in changed:
        tests_to_reset = [
            {"id": t["id"], "title": t["title"], "old_status": "pass", "new_status": "not_run"}
            for t in tests
            if t["status"] == "pass"
        ]
        risks_to_flag = open_risks

    priority = changed.get("priority")
    if priority and _RANK[priority["new"]] > _RANK[priority["old"]]:
        risks_to_flag = open_risks

    status = changed.get("status")
    if status and status["new"] == "obsolete":
        risks_to_flag = open_risks
        if tests:
            warnings.append("the requirement is now obsolete: its test cases may be retired")
    if status and status["new"] == "verified":
        not_passing = [t for t in tests if t["status"] != "pass"]
        if not tests:
            warnings.append("verified with no test cases")
        elif not_passing:
            warnings.append(f"verified while test cases are not passing: {_ids(not_passing)}")

    flagged = [
        {
            "id": r["id"],
            "title": r["title"],
            "score": r["score"],
            "level": r["level"],
            "status": r["status"],
            "already_flagged": bool(r["needs_review"]),
        }
        for r in risks_to_flag
    ]
    failing = [
        {"id": t["id"], "title": t["title"], "status": t["status"]}
        for t in tests
        if t["status"] in ("fail", "blocked")
    ]

    affected = bool(tests_to_reset or flagged or warnings)
    if not affected:
        level = "low"
    elif priority_after == "critical" or "description" in changed:
        level = "high"
    else:
        level = "medium"

    parts = [f"{requirement_id}: {', '.join(changed)} changed."]
    if tests_to_reset:
        parts.append(
            f"{_plural(len(tests_to_reset), 'passing test case')} reset to not_run "
            f"({_ids(tests_to_reset)})."
        )
    if failing:
        parts.append(f"Already failing or blocked: {_ids(failing)}.")
    if flagged:
        parts.append(f"{_plural(len(flagged), 'risk')} flagged for review ({_ids(flagged)}).")
    parts.extend(f"Note: {w}." for w in warnings)
    if not affected and not failing:
        parts.append("No test cases or risks are affected.")
    parts.append(f"Impact level: {level}.")

    return {
        "requirement_id": requirement_id,
        "level": level,
        "changed_fields": changed,
        "tests_to_reset": tests_to_reset,
        "tests_failing": failing,
        "risks_to_flag": flagged,
        "warnings": warnings,
        "summary": " ".join(parts),
    }
