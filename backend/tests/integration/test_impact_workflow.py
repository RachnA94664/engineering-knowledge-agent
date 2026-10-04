"""The automatic impact workflow: what happens when a change is confirmed.

Seed facts used here:
  REQ-009 (critical): tests TC-019 pass, TC-020 pass, TC-021 FAIL, TC-030 pass; risk RISK-003
  REQ-004 (high):     test TC-008 fails; risk RISK-002
  REQ-006 (medium):   risk RISK-011 (accepted)
  REQ-011 (medium):   risk RISK-009
"""

import pytest

from app.db import models
from app.domain.errors import Conflict, NotFound, ValidationError
from app.services import changes, knowledge, reviews
from app.services import impact as impact_service

NEW_TEXT = "Energy measurement shall be accurate to within 0.5 percent of the delivered kWh."


def propose(session, req_id, patch):
    return changes.propose_requirement_change(session, req_id, patch, proposed_by="rachna")[
        "change"
    ]["id"]


def confirm(session, req_id, patch):
    return changes.confirm_change(session, propose(session, req_id, patch), actor="rachna")


def status_of(session, test_id):
    session.expire_all()
    return session.get(models.TestCase, test_id).status


def risk_flag(session, risk_id):
    session.expire_all()
    return session.get(models.RiskItem, risk_id).needs_review


def system_entries(session):
    return [e for e in knowledge.audit_log(session, limit=100) if e["source"] == "system"]


# ---------- the main scenario ----------


def test_a_description_change_resets_passing_tests_and_flags_the_risk(seeded):
    result = confirm(seeded, "REQ-009", {"description": NEW_TEXT})

    impact = result["impact"]
    assert impact["level"] == "high"  # critical requirement + description changed
    assert [t["id"] for t in impact["tests_to_reset"]] == ["TC-019", "TC-020", "TC-030"]
    assert [t["id"] for t in impact["tests_failing"]] == ["TC-021"]
    assert [r["id"] for r in impact["risks_to_flag"]] == ["RISK-003"]
    assert "3 passing test cases reset to not_run (TC-019, TC-020, TC-030)" in impact["summary"]

    # ... and the database really changed
    assert [status_of(seeded, t) for t in ("TC-019", "TC-020", "TC-030")] == ["not_run"] * 3
    assert status_of(seeded, "TC-021") == "fail"  # a failing test is never "improved" to not_run
    assert risk_flag(seeded, "RISK-003") is True
    assert knowledge.get_requirement(seeded, "REQ-009")["description"] == NEW_TEXT


def test_every_automatic_modification_is_in_the_audit_log_as_the_system(seeded):
    result = confirm(seeded, "REQ-009", {"description": NEW_TEXT})
    change_id = result["change"]["id"]

    entries = system_entries(seeded)

    kinds = sorted((e["entity_type"], e["entity_id"], e["action"]) for e in entries)
    assert kinds == [
        ("requirement", "REQ-009", "impact"),
        ("risk", "RISK-003", "flag_review"),
        ("test_case", "TC-019", "reset"),
        ("test_case", "TC-020", "reset"),
        ("test_case", "TC-030", "reset"),
    ]
    assert all(e["actor"] == "impact-analysis" for e in entries)
    assert all(e["new_value"]["caused_by_change"] == change_id for e in entries)  # traceable
    reset = next(e for e in entries if e["entity_id"] == "TC-019")
    assert reset["old_value"] == {"status": "pass"}
    assert reset["new_value"] == {"status": "not_run", "caused_by_change": change_id}


def test_the_report_can_be_read_back_later(seeded):
    result = confirm(seeded, "REQ-009", {"description": NEW_TEXT})

    stored = knowledge.get_impact(seeded, "REQ-009")

    assert stored == result["impact"]
    assert stored["change_id"] == result["change"]["id"]


# ---------- other kinds of change ----------


def test_a_harmless_status_move_is_recorded_as_low_impact_and_changes_nothing_else(seeded):
    result = confirm(seeded, "REQ-007", {"status": "implemented"})

    assert result["impact"]["level"] == "low"
    assert result["impact"]["tests_to_reset"] == [] and result["impact"]["risks_to_flag"] == []
    assert [e["action"] for e in system_entries(seeded)] == ["impact"]  # only the report row
    assert risk_flag(seeded, "RISK-006") is False


def test_raising_the_priority_flags_risks_but_keeps_test_results(seeded):
    result = confirm(seeded, "REQ-006", {"priority": "high"})

    assert result["impact"]["level"] == "medium"
    assert [r["id"] for r in result["impact"]["risks_to_flag"]] == ["RISK-011"]
    assert result["impact"]["tests_to_reset"] == []
    assert status_of(seeded, "TC-012") == "pass"


def test_lowering_the_priority_affects_nothing(seeded):
    result = confirm(seeded, "REQ-003", {"priority": "low"})
    assert result["impact"]["level"] == "low" and result["impact"]["risks_to_flag"] == []


def test_becoming_obsolete_flags_risks_and_notes_the_tests(seeded):
    result = confirm(seeded, "REQ-011", {"status": "obsolete"})

    assert [r["id"] for r in result["impact"]["risks_to_flag"]] == ["RISK-009"]
    assert any("obsolete" in w for w in result["impact"]["warnings"])
    assert risk_flag(seeded, "RISK-009") is True


def test_verifying_a_requirement_with_failing_tests_warns_by_name(seeded):
    result = confirm(seeded, "REQ-004", {"status": "verified"})

    assert result["impact"]["warnings"] == ["verified while test cases are not passing: TC-008"]
    assert result["impact"]["level"] == "medium"
    assert status_of(seeded, "TC-008") == "fail"  # a warning, never a silent change


# ---------- idempotent ----------


def test_confirming_twice_returns_the_same_report_and_changes_nothing(seeded):
    pid = propose(seeded, "REQ-009", {"description": NEW_TEXT})
    first = changes.confirm_change(seeded, pid, actor="rachna")
    # simulate a re-run of the test case between the two confirms
    seeded.get(models.TestCase, "TC-019").status = "pass"
    seeded.commit()
    entries_before = len(knowledge.audit_log(seeded, limit=100))

    second = changes.confirm_change(seeded, pid, actor="rachna")

    assert second["already_applied"] is True
    assert second["impact"] == first["impact"]  # the same stored report
    assert status_of(seeded, "TC-019") == "pass"  # NOT reset a second time
    assert len(knowledge.audit_log(seeded, limit=100)) == entries_before  # nothing new logged


def test_an_already_flagged_risk_is_not_flagged_or_logged_again(seeded):
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})
    flag_entries = [e for e in system_entries(seeded) if e["action"] == "flag_review"]
    assert len(flag_entries) == 1

    second = confirm(seeded, "REQ-009", {"description": NEW_TEXT + " (rev 2)"})

    assert second["impact"]["risks_to_flag"][0]["already_flagged"] is True
    assert second["impact"]["tests_to_reset"] == []  # nothing is passing any more
    flag_entries = [e for e in system_entries(seeded) if e["action"] == "flag_review"]
    assert len(flag_entries) == 1  # still just the first one


# ---------- atomic: all or nothing ----------


def test_if_the_analysis_fails_the_whole_confirm_is_undone(seeded, monkeypatch):
    pid = propose(seeded, "REQ-009", {"description": NEW_TEXT})
    audit_before = len(knowledge.audit_log(seeded, limit=100))

    def boom(*args, **kwargs):
        raise RuntimeError("disk full while storing the report")

    monkeypatch.setattr(impact_service.impact_repo, "add", boom)

    with pytest.raises(RuntimeError):
        changes.confirm_change(seeded, pid, actor="rachna")

    # Nothing is half-done: not the change, not the test resets, not the flag, not the audit.
    req = knowledge.get_requirement(seeded, "REQ-009")
    assert req["version"] == 1 and req["description"] != NEW_TEXT
    assert [status_of(seeded, t) for t in ("TC-019", "TC-020", "TC-030")] == ["pass"] * 3
    assert risk_flag(seeded, "RISK-003") is False
    assert len(knowledge.audit_log(seeded, limit=100)) == audit_before
    assert [c["id"] for c in changes.list_pending_changes(seeded)] == [pid]  # still confirmable


def test_a_rejected_change_creates_no_report(seeded):
    pid = propose(seeded, "REQ-009", {"description": NEW_TEXT})
    changes.reject_change(seeded, pid, actor="rachna")

    with pytest.raises(NotFound):
        knowledge.get_impact(seeded, "REQ-009")
    assert status_of(seeded, "TC-019") == "pass"


def test_a_stale_change_creates_no_report(seeded):
    first = propose(seeded, "REQ-009", {"description": NEW_TEXT})
    second = propose(seeded, "REQ-009", {"title": "Metering accuracy"})
    changes.confirm_change(seeded, first, actor="rachna")

    with pytest.raises(Conflict):
        changes.confirm_change(seeded, second, actor="rachna")

    assert knowledge.get_impact(seeded, "REQ-009")["change_id"] == first


# ---------- reading reports ----------


def test_asking_for_a_report_before_any_confirmed_change_is_not_found(seeded):
    with pytest.raises(NotFound) as exc:
        knowledge.get_impact(seeded, "REQ-009")
    assert "confirmed change" in exc.value.message


def test_the_latest_report_wins(seeded):
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})
    second = confirm(seeded, "REQ-009", {"priority": "medium"})

    assert knowledge.get_impact(seeded, "REQ-009")["id"] == second["impact"]["id"]


def test_asking_about_an_unknown_requirement_is_not_found(seeded):
    with pytest.raises(NotFound):
        knowledge.get_impact(seeded, "REQ-099")
    with pytest.raises(ValidationError):
        knowledge.get_impact(seeded, "banana")


# ---------- a person reviews a flagged risk ----------


def test_a_person_can_clear_the_flag_and_it_is_logged(seeded):
    confirm(seeded, "REQ-009", {"description": NEW_TEXT})

    risk = reviews.mark_risk_reviewed(seeded, "RISK-003", actor="rachna")

    assert risk["needs_review"] is False and risk_flag(seeded, "RISK-003") is False
    entry = knowledge.audit_log(seeded, entity_id="RISK-003")[0]
    assert (entry["action"], entry["actor"], entry["source"]) == ("review", "rachna", "ui")
    assert entry["old_value"] == {"needs_review": True}


def test_reviewing_an_unflagged_risk_changes_nothing(seeded):
    before = len(knowledge.audit_log(seeded, limit=100))
    risk = reviews.mark_risk_reviewed(seeded, "RISK-001", actor="rachna")

    assert risk["needs_review"] is False
    assert len(knowledge.audit_log(seeded, limit=100)) == before


def test_reviewing_rejects_unknown_risks_bad_ids_and_blank_actors(seeded):
    with pytest.raises(NotFound):
        reviews.mark_risk_reviewed(seeded, "RISK-099", actor="rachna")
    with pytest.raises(ValidationError):
        reviews.mark_risk_reviewed(seeded, "banana", actor="rachna")
    with pytest.raises(ValidationError):
        reviews.mark_risk_reviewed(seeded, "RISK-003", actor="  ")
