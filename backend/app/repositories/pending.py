"""All SQL about pending changes lives here."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PendingChange


def add(
    session: Session,
    *,
    entity_type: str,
    entity_id: str,
    patch: dict,
    base_version: int,
    proposed_by: str,
) -> PendingChange:
    """Store a proposed change as ``pending``. Part of the CALLER's transaction.

    Args:
        session: The database session.
        entity_type: What is being changed, for example ``"requirement"``.
        entity_id: The ID of the record being changed.
        patch: The fields to change and their new values (stored as JSON text).
        base_version: The version of the record the proposal was based on.
        proposed_by: Who proposed it (a person's name or the agent's name).

    Returns:
        The new row, with its ``id`` assigned (nothing is committed yet).
    """
    change = PendingChange(
        entity_type=entity_type,
        entity_id=entity_id,
        proposed_patch=json.dumps(patch, sort_keys=True),
        base_version=base_version,
        proposed_by=proposed_by,
        status="pending",
    )
    session.add(change)
    session.flush()  # assigns change.id without committing
    return change


def get(session: Session, change_id: int) -> PendingChange | None:
    """Get one change by its ID.

    Args:
        session: The database session.
        change_id: The ID of the change.

    Returns:
        The change, or None if there is no such change.
    """
    return session.get(PendingChange, change_id)


def list_by_status(session: Session, status: str = "pending") -> list[PendingChange]:
    """List the changes that have a given status, oldest first.

    Args:
        session: The database session.
        status: ``pending``, ``applied``, ``rejected`` or ``expired``.

    Returns:
        The matching changes ordered by ID.
    """
    return list(
        session.scalars(
            select(PendingChange).where(PendingChange.status == status).order_by(PendingChange.id)
        )
    )
