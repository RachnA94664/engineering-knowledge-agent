"""Small input checks shared by the services."""

from app.domain import enums
from app.domain.errors import ValidationError


def check_who(actor: object, source: object) -> None:
    """Check that a write says WHO did it and from WHERE (both go into the audit log).

    Args:
        actor: The name of the person or agent doing it. Must not be blank.
        source: Where it came from. Must be one of ``ui``, ``agent`` or ``system``.

    Raises:
        ValidationError: If the actor is blank or the source is not an allowed one.
    """
    if not isinstance(actor, str) or not actor.strip():
        raise ValidationError("actor must not be empty")
    if source not in enums.AUDIT_SOURCES:
        raise ValidationError(f"source must be one of {enums.AUDIT_SOURCES}, got {source!r}")
