"""Every timestamp the system returns is UTC and looks the same, however it was produced.

Regression test: SQLite drops timezones, so a value read back from the database used to differ
from the one returned right after saving ("...+00:00" versus no suffix).
"""

from datetime import UTC, datetime

import pytest

from app.db import models
from app.services import changes, knowledge

NEW_TEXT = "Energy measurement shall be accurate to within 0.5 percent of the delivered kWh."


def is_utc(stamp: str) -> bool:
    return stamp is not None and stamp.endswith("+00:00")


def test_requirement_timestamps_read_from_the_database_carry_utc(seeded):
    requirement = knowledge.get_requirement(seeded, "REQ-001")
    assert is_utc(requirement["created_at"]) and is_utc(requirement["updated_at"])


def test_a_value_just_saved_and_the_same_value_read_back_look_identical(seeded):
    proposal = changes.propose_requirement_change(
        seeded, "REQ-009", {"description": NEW_TEXT}, proposed_by="rachna"
    )
    just_saved = proposal["change"]["created_at"]

    seeded.expire_all()  # force a real read from the database
    read_back = changes.list_pending_changes(seeded)[0]["created_at"]

    assert just_saved == read_back and is_utc(just_saved)


def test_confirming_twice_returns_a_report_that_looks_exactly_the_same(seeded):
    pid = changes.propose_requirement_change(
        seeded, "REQ-009", {"description": NEW_TEXT}, proposed_by="rachna"
    )["change"]["id"]
    first = changes.confirm_change(seeded, pid, actor="rachna")
    seeded.expire_all()

    second = changes.confirm_change(seeded, pid, actor="rachna")

    assert first["impact"]["created_at"] == second["impact"]["created_at"]
    assert is_utc(first["impact"]["created_at"])
    assert is_utc(first["change"]["resolved_at"]) and is_utc(second["change"]["resolved_at"])


def test_audit_timestamps_are_utc(seeded):
    changes.propose_requirement_change(
        seeded, "REQ-009", {"title": "Metering"}, proposed_by="rachna"
    )
    assert all(is_utc(entry["ts"]) for entry in knowledge.audit_log(seeded))


def test_a_timestamp_without_a_timezone_is_refused(seeded):
    seeded.add(
        models.AuditLog(
            actor="x",
            source="ui",
            entity_type="requirement",
            entity_id="REQ-001",
            action="propose",
            ts=datetime(2026, 1, 1, 12, 0, 0),
        )
    )
    with pytest.raises(Exception, match="timezone"):
        seeded.commit()
    seeded.rollback()


def test_a_timestamp_in_another_timezone_is_stored_as_utc(seeded):
    from datetime import timedelta, timezone

    plus_two = timezone(timedelta(hours=2))
    entry = models.AuditLog(
        actor="x",
        source="ui",
        entity_type="requirement",
        entity_id="REQ-001",
        action="propose",
        ts=datetime(2026, 1, 1, 14, 0, 0, tzinfo=plus_two),
    )
    seeded.add(entry)
    seeded.commit()
    seeded.expire_all()

    assert seeded.get(models.AuditLog, entry.id).ts == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
