"""The FastAPI application.

Run it:  uvicorn app.main:app --reload
Docs:    http://localhost:8000/docs
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.deps import SessionDep
from app.api.errors import register_error_handlers
from app.api.routes_changes import router as changes_router
from app.api.routes_chat import router as chat_router
from app.api.routes_read import router as read_router
from app.api.schemas import HealthOut
from app.core.config import get_settings
from app.core.tracing import configure_tracing
from app.db.schema import schema_problem
from app.db.session import SessionLocal

logger = logging.getLogger("app")


def configure_app_logging() -> None:
    """Show the application's own INFO messages next to uvicorn's.

    Without this, only warnings would appear, so you could not see which prompt source or
    tracing mode is in use. Safe to call more than once.
    """
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     [%(name)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """On start-up, say clearly if the database is behind the code (it still starts)."""
    try:
        with SessionLocal() as session:
            problem = schema_problem(session)
        if problem:
            logger.error("STARTUP WARNING: %s", problem)
    except Exception:  # a start-up check must never stop the app from starting
        logger.exception("could not check the database schema version")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_app_logging()
    configure_tracing(settings)  # LangSmith reads the process environment: sync it first
    app = FastAPI(
        title="Engineering Knowledge Agent API",
        version="0.1.0",
        lifespan=lifespan,
        description=(
            "Requirements, test cases and risk items. Data is changed only through "
            "propose -> confirm, and every change is written to the audit log."
        ),
    )

    # Browsers only allow the frontend to call us if its address is listed here.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(read_router)
    app.include_router(changes_router)
    app.include_router(chat_router)

    @app.get("/health", response_model=HealthOut, tags=["system"])
    def health(session: SessionDep, response: Response):
        """Is the API up, can it reach the database, and is the database up to date?"""
        try:
            session.execute(text("SELECT 1"))
        except Exception:
            response.status_code = 503
            return {"status": "degraded", "database": "unreachable"}
        problem = schema_problem(session)
        if problem:
            response.status_code = 503
            return {"status": "degraded", "database": problem}
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
