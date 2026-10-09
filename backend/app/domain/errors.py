"""Domain errors: what can go wrong in business rules.

The API layer (Phase 5) maps these to HTTP codes. Keeping them here means the
rules never depend on FastAPI.
"""


class DomainError(Exception):
    """Base class. `code` is a stable machine-readable name."""

    code = "domain_error"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(DomainError):
    """The input breaks a rule: a bad value, a missing field or a wrong format (HTTP 422)."""

    code = "validation_error"


class InvalidTransition(DomainError):
    """A status change that the requirement lifecycle does not allow (HTTP 409)."""

    code = "invalid_transition"


class NotFound(DomainError):
    """The record that was asked for does not exist (HTTP 404)."""

    code = "not_found"


class Conflict(DomainError):
    """The request clashes with the current state, for example a stale proposal (HTTP 409)."""

    code = "conflict"


class ServiceUnavailable(DomainError):
    """An outside service (such as the AI provider) cannot be used right now."""

    code = "service_unavailable"
