"""The migrations must build the full schema from nothing (a fresh clone) AND upgrade a
database that already holds data (a real user's database)."""

import json
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[2]
SEED = BACKEND / "data" / "seed_raw.json"

# The revision just BEFORE the impact workflow added its table and column.
BEFORE_IMPACT = "13cf4b0d8c97"


def alembic_config(db_file: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    return cfg


def test_alembic_upgrade_head_creates_all_tables(tmp_path):
    db_file = tmp_path / "fresh.db"

    command.upgrade(alembic_config(db_file), "head")

    with sqlite3.connect(db_file) as conn:
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert {
        "requirements",
        "test_cases",
        "risk_items",
        "requirement_risks",
        "audit_log",
        "pending_changes",
        "impact_reports",
    } <= tables


def fill_old_schema(db_file: Path) -> dict:
    """Insert the seed data with plain SQL, the way an existing database would hold it."""
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    now = "2026-10-04 00:00:00"
    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for r in seed["requirements"]:
            conn.execute(
                "insert into requirements (id,title,description,priority,status,version,"
                "created_at,updated_at) values (?,?,?,?,?,1,?,?)",
                (r["id"], r["title"], r["description"], r["priority"], r["status"], now, now),
            )
        for r in seed["risk_items"]:
            conn.execute(
                "insert into risk_items (id,title,description,severity,likelihood,status) "
                "values (?,?,?,?,?,?)",
                (
                    r["id"],
                    r["title"],
                    r["description"],
                    r["severity"],
                    r["likelihood"],
                    r["status"],
                ),
            )
        for t in seed["test_cases"]:
            conn.execute(
                "insert into test_cases (id,requirement_id,title,steps,expected_result,status) "
                "values (?,?,?,?,?,?)",
                (
                    t["id"],
                    t["requirement_id"],
                    t["title"],
                    t["steps"],
                    t["expected_result"],
                    t["status"],
                ),
            )
        for link in seed["requirement_risks"]:
            conn.execute(
                "insert into requirement_risks (requirement_id,risk_id) values (?,?)",
                (link["requirement_id"], link["risk_id"]),
            )
    return counts(db_file)


def counts(db_file: Path) -> dict:
    with sqlite3.connect(db_file) as conn:
        return {
            t: conn.execute(f"select count(*) from {t}").fetchone()[0]
            for t in ("requirements", "test_cases", "risk_items", "requirement_risks")
        }


def test_upgrading_a_database_that_already_has_data_keeps_every_row(tmp_path):
    """Regression test: a table rebuild used to fail because other tables point at risk_items."""
    db_file = tmp_path / "existing.db"
    cfg = alembic_config(db_file)
    command.upgrade(cfg, BEFORE_IMPACT)
    before = fill_old_schema(db_file)
    assert before == {
        "requirements": 15,
        "test_cases": 30,
        "risk_items": 12,
        "requirement_risks": 16,
    }

    command.upgrade(cfg, "head")

    assert counts(db_file) == before  # nothing lost
    with sqlite3.connect(db_file) as conn:
        flags = conn.execute("select needs_review, count(*) from risk_items group by 1").fetchall()
        triggers = {
            r[0] for r in conn.execute("select name from sqlite_master where type='trigger'")
        }
    assert flags == [(0, 12)]  # every existing risk starts as "not flagged"
    assert {"audit_log_no_update", "audit_log_no_delete"} <= triggers  # protection survives


def test_the_impact_migration_can_be_rolled_back_without_losing_data(tmp_path):
    db_file = tmp_path / "rollback.db"
    cfg = alembic_config(db_file)
    command.upgrade(cfg, BEFORE_IMPACT)
    before = fill_old_schema(db_file)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, BEFORE_IMPACT)

    assert counts(db_file) == before
    with sqlite3.connect(db_file) as conn:
        columns = [r[1] for r in conn.execute("pragma table_info(risk_items)")]
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert "needs_review" not in columns and "impact_reports" not in tables
