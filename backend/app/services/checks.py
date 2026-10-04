"""Small input checks shared by the services."""

from app.domain import enums
from app.domain.errors import ValidationError


def check_who(actor: object, source: object) -> None:
    """Every write must say WHO did it and from WHERE (for the audit log)."""
    if not isinstance(actor, str) or not actor.strip():
        raise ValidationError("actor must not be empty")
    if source not in enums.AUDIT_SOURCES:
        raise ValidationError(f"source must be one of {enums.AUDIT_SOURCES}, got {source!r}")
