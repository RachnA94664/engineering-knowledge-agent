import pytest

from app.domain.impact import analyze

# REQ-009 from the seed data: 3 passing tests, 1 failing; one linked risk.
TESTS = [
    {"id": "TC-019", "title": "Meter accuracy at 7 kW", "status": "pass"},
    {"id": "TC-020", "title": "Meter accuracy at 22 kW", "status": "pass"},
    {"id": "TC-021", "title": "Meter accuracy at low current", "status": "fail"},
    {"id": "TC-030", "title": "Meter data retention", "status": "pass"},
]
RISK = {
    "id": "RISK-003",
    "title": "Inaccurate billing",
    "score": 12,
    "level": "medium",
    "status": "open",
    "needs_review": False,
}


def change(**fields):
    return {name: {"old": old, "new": new} for name, (old, new) in fields.items()}


def run(changed, priority="critical", tests=TESTS, risks=(RISK,)):
    return analyze("REQ-009", changed, priority, list(tests), list(risks))


# ---------- description changes: the big one ----------


def test_a_description_change_resets_only_the_passing_tests():
    r = run(change(description=("old text", "new text")))
    assert [t["id"] for t in r["tests_to_reset"]] == ["TC-019", "TC-020", "TC-030"]
    assert all(
        t["old_status"] == "pass" and t["new_status"] == "not_run" for t in r["tests_to_reset"]
    )


def test_a_failing_test_is_reported_but_not_reset():
    r = run(change(description=("a", "b")))
    assert [t["id"] for t in r["tests_failing"]] == ["TC-021"]
    assert "TC-021" not in [t["id"] for t in r["tests_to_reset"]]


def test_a_description_change_flags_the_linked_risks():
    r = run(change(description=("a", "b")))
    assert [x["id"] for x in r["risks_to_flag"]] == ["RISK-003"]
    assert r["risks_to_flag"][0]["already_flagged"] is False


def test_closed_risks_are_never_flagged():
    closed = dict(RISK, status="closed")
    assert run(change(description=("a", "b")), risks=[closed])["risks_to_flag"] == []


def test_an_already_flagged_risk_is_still_listed_but_marked():
    flagged = dict(RISK, needs_review=True)
    r = run(change(description=("a", "b")), risks=[flagged])
    assert r["risks_to_flag"][0]["already_flagged"] is True


# ---------- priority ----------


@pytest.mark.parametrize(
    "old,new,flags",
    [
        ("medium", "high", True),
        ("low", "critical", True),
        ("high", "medium", False),
        ("high", "low", False),
    ],
)
def test_only_raising_the_priority_flags_risks(old, new, flags):
    r = run(change(priority=(old, new)), priority=new)
    assert bool(r["risks_to_flag"]) is flags
    assert r["tests_to_reset"] == []  # a priority change never invalidates test results


# ---------- status ----------


def test_becoming_obsolete_flags_risks_and_notes_the_tests():
    r = run(change(status=("implemented", "obsolete")), priority="high")
    assert [x["id"] for x in r["risks_to_flag"]] == ["RISK-003"]
    assert any("obsolete" in w for w in r["warnings"])
    assert r["tests_to_reset"] == []


def test_verifying_with_non_passing_tests_warns_and_names_them():
    r = run(change(status=("implemented", "verified")), priority="high")
    assert r["warnings"] == ["verified while test cases are not passing: TC-021"]
    assert r["level"] == "medium"


def test_verifying_with_no_tests_warns():
    r = run(change(status=("implemented", "verified")), priority="medium", tests=[], risks=[])
    assert r["warnings"] == ["verified with no test cases"]


def test_a_harmless_status_move_affects_nothing():
    r = run(change(status=("approved", "implemented")), priority="high")
    assert r["level"] == "low"
    assert r["tests_to_reset"] == [] and r["risks_to_flag"] == [] and r["warnings"] == []
    assert "Impact level: low." in r["summary"]


def test_a_title_change_affects_nothing():
    r = run(change(title=("Old title", "New title")), priority="critical")
    assert r["level"] == "low"
    assert r["tests_to_reset"] == [] and r["risks_to_flag"] == []


# ---------- impact level ----------


def test_critical_requirement_with_something_affected_is_high():
    assert run(change(description=("a", "b")), priority="critical")["level"] == "high"


def test_a_description_change_is_high_even_when_the_requirement_is_not_critical():
    assert run(change(description=("a", "b")), priority="medium")["level"] == "high"


def test_a_noncritical_non_description_effect_is_medium():
    r = run(change(priority=("medium", "high")), priority="high")
    assert r["level"] == "medium"


def test_critical_requirement_with_nothing_affected_stays_low():
    r = run(change(title=("a", "b")), priority="critical", tests=[], risks=[])
    assert r["level"] == "low"


def test_a_requirement_with_no_links_has_no_effect_even_if_the_description_changes():
    r = run(change(description=("a", "b")), tests=[], risks=[])
    assert r["level"] == "low"
    assert "No test cases or risks are affected." in r["summary"]


# ---------- the summary sentence ----------


def test_the_summary_names_the_real_ids():
    summary = run(change(description=("a", "b")))["summary"]
    assert "REQ-009: description changed." in summary
    assert "3 passing test cases reset to not_run (TC-019, TC-020, TC-030)." in summary
    assert "Already failing or blocked: TC-021." in summary
    assert "1 risk flagged for review (RISK-003)." in summary
    assert summary.endswith("Impact level: high.")


def test_the_summary_uses_singular_for_one_item():
    one_test = [{"id": "TC-001", "title": "t", "status": "pass"}]
    summary = run(change(description=("a", "b")), tests=one_test)["summary"]
    assert "1 passing test case reset" in summary
