"""Turn database objects into plain dictionaries (safe to return from the API or agents)."""

import json

from app.db import models
from app.domain.risk import risk_level, risk_score


def _iso(value) -> str | None:
    """Format a timestamp as ISO 8601 text, keeping None as None.

    Args:
        value: A timestamp or None.

    Returns:
        The ISO 8601 text, or None.
    """
    return value.isoformat() if value is not None else None


def requirement_to_dict(req: models.Requirement) -> dict:
    """Describe a requirement as a plain dictionary.

    Args:
        req: The requirement row.

    Returns:
        Its fields, with timestamps as ISO 8601 text.
    """
    return {
        "id": req.id,
        "title": req.title,
        "description": req.description,
        "priority": req.priority,
        "status": req.status,
        "version": req.version,
        "created_at": _iso(req.created_at),
        "updated_at": _iso(req.updated_at),
    }


def testcase_to_dict(tc: models.TestCase) -> dict:
    """Describe a test case as a plain dictionary.

    Args:
        tc: The test case row.

    Returns:
        Its fields.
    """
    return {
        "id": tc.id,
        "requirement_id": tc.requirement_id,
        "title": tc.title,
        "steps": tc.steps,
        "expected_result": tc.expected_result,
        "status": tc.status,
    }


def risk_to_dict(risk: models.RiskItem) -> dict:
    """Describe a risk item as a plain dictionary.

    Args:
        risk: The risk row.

    Returns:
        Its fields plus the derived ``score`` (severity x likelihood) and ``level``. Those two
        are calculated here and never stored.
    """
    score = risk_score(risk.severity, risk.likelihood)
    return {
        "id": risk.id,
        "title": risk.title,
        "description": risk.description,
        "severity": risk.severity,
        "likelihood": risk.likelihood,
        "status": risk.status,
        "score": score,  # derived, never stored
        "level": risk_level(score),  # derived, never stored
        "needs_review": risk.needs_review,  # set by the impact analysis; cleared by a person
    }


def change_to_dict(change: models.PendingChange) -> dict:
    """Describe a pending change as a plain dictionary.

    Args:
        change: The pending-change row.

    Returns:
        Its fields, with the stored JSON patch decoded into a dictionary.
    """
    return {
        "id": change.id,
        "entity_type": change.entity_type,
        "entity_id": change.entity_id,
        "patch": json.loads(change.proposed_patch),
        "base_version": change.base_version,
        "proposed_by": change.proposed_by,
        "status": change.status,
        "created_at": _iso(change.created_at),
        "resolved_at": _iso(change.resolved_at),
    }


def audit_to_dict(entry: models.AuditLog) -> dict:
    """Describe an audit-log entry as a plain dictionary.

    Args:
        entry: The audit-log row.

    Returns:
        Its fields, with the stored JSON values decoded.
    """
    return {
        "id": entry.id,
        "ts": _iso(entry.ts),
        "actor": entry.actor,
        "source": entry.source,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "action": entry.action,
        "old_value": json.loads(entry.old_value) if entry.old_value else None,
        "new_value": json.loads(entry.new_value) if entry.new_value else None,
        "request_id": entry.request_id,
    }


def impact_to_dict(row: models.ImpactReport) -> dict:
    """Describe a stored impact report as a plain dictionary.

    Args:
        row: The impact-report row.

    Returns:
        The stored report with its row id, change id and creation time added.
    """
    return {
        "id": row.id,
        "change_id": row.change_id,
        "created_at": _iso(row.created_at),
        **json.loads(row.report),
    }
