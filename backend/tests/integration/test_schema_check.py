"""The app must say clearly when the database is behind the code (new code, old database)."""

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db.schema import current_revision, head_revision, schema_problem
from app.db.session import get_session, make_engine
from app.main import app

BEFORE_IMPACT = "13cf4b0d8c97"  # the revision before the impact workflow's migration


def old_database(tmp_path, revision=BEFORE_IMPACT):
    """A database migrated only up to `revision` (what a user has before running upgrade)."""
    from tests.integration.test_migrations import BACKEND

    db_file = tmp_path / "old.db"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    command.upgrade(cfg, revision)
    return make_engine(f"sqlite:///{db_file}")


# ---------- the comparison itself ----------


def test_a_migrated_database_matches_the_code(session):
    assert current_revision(session) == head_revision()
    assert schema_problem(session) is None


def test_the_head_revision_is_the_newest_migration():
    assert head_revision() != BEFORE_IMPACT and len(head_revision()) >= 8


def test_an_old_database_is_reported_with_the_fix(tmp_path):
    engine = old_database(tmp_path)
    with sessionmaker(bind=engine)() as session:
        problem = schema_problem(session)

    assert BEFORE_IMPACT in problem and head_revision() in problem
    assert "alembic upgrade head" in problem
    engine.dispose()


def test_a_database_that_was_never_migrated_is_reported(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")  # no tables at all
    with sessionmaker(bind=engine)() as session:
        assert current_revision(session) is None
        assert "has never been migrated" in schema_problem(session)
    engine.dispose()


# ---------- /health ----------


def test_health_is_ok_when_the_database_is_current(api):
    r = api.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "ok"}


def test_health_says_what_to_do_when_the_database_is_old(tmp_path):
    engine = old_database(tmp_path)
    factory = sessionmaker(bind=engine)

    def old_session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = old_session
    try:
        r = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert "out of date" in body["database"] and "alembic upgrade head" in body["database"]


def test_health_still_works_for_an_unreachable_database():
    class Broken:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("cannot connect")

    def broken_session():
        yield Broken()

    app.dependency_overrides[get_session] = broken_session
    try:
        r = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 503 and r.json() == {"status": "degraded", "database": "unreachable"}


def test_the_health_check_does_not_change_the_database(session):
    session.execute(text("SELECT 1"))
    before = session.execute(text("SELECT count(*) FROM audit_log")).scalar()
    schema_problem(session)
    assert session.execute(text("SELECT count(*) FROM audit_log")).scalar() == before
