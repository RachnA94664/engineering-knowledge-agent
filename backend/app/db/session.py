"""Database engine and session factory."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    """Create the database engine.

    For SQLite this also switches foreign keys on for every new connection (SQLite ignores
    them otherwise) and allows the connection to be used from FastAPI's worker threads.

    Args:
        url: The database URL. Defaults to ``DATABASE_URL`` from the settings.

    Returns:
        The SQLAlchemy engine.
    """
    url = url or get_settings().database_url
    kwargs: dict = {}
    if url.startswith("sqlite"):
        # FastAPI handles each request in a worker thread. Each request gets its own
        # session (and so its own connection use), so sharing the pool across threads is safe.
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)

    if engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys unless this is switched on for EVERY
        # new connection. This listener does it automatically.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Give a request its own database session and always close it afterwards.

    Yields:
        An open session, valid for the duration of one request.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
