"""Is the database at the migration version this code expects?

Why this exists: after you pull new code, the database may still be at an OLD migration. The
code then asks for a column or table that is not there and every request that touches it
fails with a bare "500 internal error". Comparing the two revisions lets /health say plainly:
"the database is out of date: run alembic upgrade head".
"""

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[2]


@lru_cache
def head_revision() -> str:
    """The newest migration shipped with this code."""
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None, "the project has no migrations"
    return head


def current_revision(session: Session) -> str | None:
    """The migration the database is at, or None if it was never migrated."""
    try:
        return session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # the alembic_version table does not exist
        session.rollback()
        return None


def schema_problem(session: Session) -> str | None:
    """A plain-English description of the problem, or None if the schema is current."""
    current, head = current_revision(session), head_revision()
    if current == head:
        return None
    where = "has never been migrated" if current is None else f"is at revision {current}"
    return (
        f"the database schema is out of date (it {where}, the code expects {head}): "
        "run 'alembic upgrade head'"
    )
