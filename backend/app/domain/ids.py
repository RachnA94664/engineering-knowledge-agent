"""ID format rules: REQ-001, TC-001, RISK-001."""

import re

from app.domain.errors import ValidationError

_PATTERNS = {
    "requirement": re.compile(r"REQ-[0-9]{3}"),
    "test_case": re.compile(r"TC-[0-9]{3}"),
    "risk": re.compile(r"RISK-[0-9]{3}"),
}


def is_valid_id(kind: str, value: object) -> bool:
    """Tell whether a value is a correctly formed ID of the given kind.

    Args:
        kind: What the ID identifies: ``"requirement"``, ``"test_case"`` or ``"risk"``.
        value: The value to check. Anything is accepted; only a matching string passes.

    Returns:
        True if ``value`` is a string that fully matches the format of ``kind`` (for
        example ``REQ-001``), otherwise False.

    Raises:
        ValueError: If ``kind`` is not one of the three known kinds.
    """
    if kind not in _PATTERNS:
        raise ValueError(f"unknown kind: {kind!r}")
    return isinstance(value, str) and _PATTERNS[kind].fullmatch(value) is not None


def ensure_valid_id(kind: str, value: object) -> str:
    """Check an ID and return it unchanged, or explain what is wrong with it.

    Args:
        kind: What the ID identifies: ``"requirement"``, ``"test_case"`` or ``"risk"``.
        value: The value to check.

    Returns:
        The same ``value``, now known to be a correctly formed ID string.

    Raises:
        ValidationError: If ``value`` is not a valid ID of that kind.
        ValueError: If ``kind`` is not one of the three known kinds.
    """
    if not is_valid_id(kind, value):
        raise ValidationError(
            f"invalid {kind} id: {value!r}", details={"kind": kind, "value": value}
        )
    return value  # type: ignore[return-value]
