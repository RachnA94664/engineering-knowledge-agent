"""All SQL about the audit log lives here. The table is append-only."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog


def _dump(value: object) -> str | None:
    return None if value is None else json.dumps(value, sort_keys=True, default=str)


def add_entry(
    session: Session,
    *,
    actor: str,
    source: str,
    entity_type: str,
    entity_id: str,
    action: str,
    old: object = None,
    new: object = None,
    request_id: str | None = None,
) -> AuditLog:
    """Add an audit row to the CURRENT transaction (the caller commits).

    Args:
        session: The database session.
        actor: Who did it (a person's name, the agent's name, or ``impact-analysis``).
        source: Where it came from: ``ui``, ``agent`` or ``system``.
        entity_type: The kind of record that changed, for example ``requirement``.
        entity_id: The ID of the record that changed.
        action: What happened, for example ``update`` or ``flag_review``.
        old: The value before the change (stored as JSON text), if any.
        new: The value after the change (stored as JSON text), if any.
        request_id: An optional ID that ties several rows to one request.

    Returns:
        The new row (not yet committed).
    """
    entry = AuditLog(
        actor=actor,
        source=source,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=_dump(old),
        new_value=_dump(new),
        request_id=request_id,
    )
    session.add(entry)
    return entry


def list_recent(session: Session, limit: int = 50, entity_id: str | None = None) -> list[AuditLog]:
    """List the newest audit entries.

    Args:
        session: The database session.
        limit: The maximum number of entries to return.
        entity_id: If given, only entries about this record (for example ``REQ-001``).

    Returns:
        The entries, newest first.
    """
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
    return list(session.scalars(query))
