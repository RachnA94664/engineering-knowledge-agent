"""Read simple change commands with plain rules, so the AI is not needed for them.

    "Set REQ-006 priority to high"          -> {"requirement_id": "REQ-006", "priority": "high"}
    "Change the status of REQ-007 to verified"
    "Mark REQ-002 as obsolete"               (a bare "mark ... as" means a status change)

Why: small AI models sometimes call a tool with wrong argument names. For a command this
simple, rules read it exactly, instantly and for free. The result is still only a PROPOSAL,
sent through the same tool and the same checks as an AI-made one. Anything the rules cannot
read exactly (unusual wording, several changes at once, free text) returns None and goes to
the AI as before.
"""

import re

from app.domain.enums import PRIORITIES, REQUIREMENT_STATUSES

_ID = r"(?P<id>REQ-[0-9]{3})"
_VERB = r"(?:please\s+)?(?:set|change|update|mark|move|make)"
_VALUE = r"(?P<value>[A-Za-z_]+)"
_END = r"\s*[.!]?\s*$"
_FIELD = r"(?P<field>status|priority)"

_PATTERNS = (
    # "Set the priority of REQ-006 to high"
    re.compile(
        rf"^\s*{_VERB}\s+(?:the\s+)?{_FIELD}\s+of\s+{_ID}\s+(?:to|as|=)\s+{_VALUE}{_END}", re.I
    ),
    # "Set REQ-006 priority to high" / "Set REQ-006's status to verified"
    re.compile(rf"^\s*{_VERB}\s+{_ID}(?:'s)?\s+{_FIELD}\s+(?:to|as|=)\s+{_VALUE}{_END}", re.I),
    # "Mark REQ-002 as obsolete" (a status change)
    re.compile(rf"^\s*(?:please\s+)?mark\s+{_ID}\s+as\s+{_VALUE}{_END}", re.I),
)

_ALLOWED = {"status": REQUIREMENT_STATUSES, "priority": PRIORITIES}


def parse_simple_update(message: str) -> dict | None:
    """Return the tool arguments for a simple, exact change command, or None."""
    for pattern in _PATTERNS:
        match = pattern.match(message)
        if not match:
            continue
        field = (match.groupdict().get("field") or "status").lower()
        value = match.group("value").lower()
        if value not in _ALLOWED[field]:
            return None  # not a valid value: let the normal path explain it
        return {"requirement_id": match.group("id").upper(), field: value}
    return None
