"""Turn errors into HTTP responses with ONE consistent JSON shape.

Every error response looks like this::

    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import (
    Conflict,
    DomainError,
    InvalidTransition,
    NotFound,
    ServiceUnavailable,
    ValidationError,
)

logger = logging.getLogger("app")

# Order matters only for subclasses; none of these inherit from each other.
STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFound: 404,
    ValidationError: 422,
    InvalidTransition: 409,  # the request clashes with the current state
    Conflict: 409,
    ServiceUnavailable: 503,  # e.g. the AI provider is down or no API key is set
}


def error_response(status: int, code: str, message: str, details: dict | None = None):
    """Build an error response in the standard shape.

    Args:
        status: The HTTP status code.
        code: A stable machine-readable name, for example ``not_found``.
        message: A sentence a person can read.
        details: Optional extra facts (for example the allowed status moves).

    Returns:
        The JSON response.
    """
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return JSONResponse(status_code=status, content=jsonable_encoder(body))


async def domain_error_handler(_: Request, exc: DomainError):
    """Answer a business-rule error with its HTTP status (404, 409, 422 or 503).

    Args:
        _: The request (unused).
        exc: The domain error that was raised.

    Returns:
        The standard JSON error response.
    """
    status = next((s for cls, s in STATUS_BY_ERROR.items() if isinstance(exc, cls)), 400)
    return error_response(status, exc.code, exc.message, exc.details)


async def request_validation_handler(_: Request, exc: RequestValidationError):
    """Answer a malformed request (wrong shape or types) with HTTP 422.

    Args:
        _: The request (unused).
        exc: FastAPI's validation error, which lists every problem found.

    Returns:
        The standard JSON error response, with the problems under ``details.errors``.
    """
    return error_response(
        422,
        "validation_error",
        "the request is not valid",
        {"errors": jsonable_encoder(exc.errors())},
    )


async def http_error_handler(_: Request, exc: StarletteHTTPException):
    """Answer a plain HTTP error (unknown URL, wrong method) in the standard shape.

    Args:
        _: The request (unused).
        exc: The HTTP error, for example a 404 for an unknown URL or a 405 for a wrong method.

    Returns:
        The standard JSON error response with the code ``http_error``.
    """
    return error_response(exc.status_code, "http_error", str(exc.detail))


async def unhandled_error_handler(_: Request, exc: Exception):
    """Answer any unexpected error with HTTP 500 and nothing that could leak internals.

    The real cause is written to the server log.

    Args:
        _: The request (unused).
        exc: The unexpected error.

    Returns:
        The standard JSON error response with the code ``internal_error``.
    """
    logger.exception("unhandled error")
    return error_response(500, "internal_error", "something went wrong on the server")


def register_error_handlers(app: FastAPI) -> None:
    """Install the four error handlers on the application.

    Args:
        app: The FastAPI application.
    """
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
