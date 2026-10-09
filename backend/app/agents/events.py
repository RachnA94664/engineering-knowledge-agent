"""Read the tool results out of a finished (or stopped) graph run.

The graph state holds LangChain messages. Every tool run leaves a ToolMessage whose
`artifact` is the raw outcome ({"ok": ..., "result" | "error": ...}). From those we build
the three things the user and the safety checks need: the evidence, the trace, the records.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


def message_text(content: Any) -> str:
    """Get a message's text, whether the provider returned a string or a list of parts.

    Args:
        content: The ``content`` of a LangChain message.

    Returns:
        The text, or an empty string if the content has no text.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p if isinstance(p, str) else p.get("text", "") for p in content]
        return "".join(parts)
    return ""


@dataclass
class ToolEvent:
    """One tool run, recorded for the user to see."""

    name: str
    arguments: dict
    ok: bool
    result: Any = None
    error: str | None = None
    # Why it failed: our own error code (e.g. "invalid_transition"), or "invalid_call" when the
    # framework rejected the AI's call (wrong argument names, unknown tool) before our code ran.
    code: str | None = None


def clean_framework_error(text: str) -> str:
    """Shorten the framework's rejection text to the useful part.

    For example ``new_priority: Extra inputs are not permitted``, with no tool name and no
    dump of the arguments.

    Args:
        text: The framework's error text for a tool call it refused to run.

    Returns:
        A short, readable reason.
    """
    # The framework embeds its message inside an exception's text, so line breaks can arrive as
    # the two characters backslash + n. Turn them back into real breaks first.
    text = text.replace("\\n", "\n")
    match = re.search(r"with error:\s*(.*?)\s*Please fix", text, re.DOTALL)
    if match:
        return " ".join(match.group(1).split())
    match = re.search(r"(\S+ is not a valid tool)", text)
    if match:
        return match.group(1)
    return " ".join(text.split())[:200]


def tool_events(messages: list[BaseMessage]) -> list[ToolEvent]:
    """Turn the tool messages of a run into one ``ToolEvent`` per tool call.

    Args:
        messages: The messages of a finished (or stopped) graph run.

    Returns:
        The tool runs in order. A call the framework refused before our code ran (bad
        arguments, unknown tool) becomes a failed event with the code ``invalid_call``.
    """
    arguments_by_call_id: dict[str, dict] = {}
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                arguments_by_call_id[call["id"]] = call["args"]

    events: list[ToolEvent] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        arguments = arguments_by_call_id.get(message.tool_call_id, {})
        outcome = message.artifact
        if isinstance(outcome, dict) and "ok" in outcome:
            ok = bool(outcome["ok"])
            error = None if ok else outcome["error"]["message"]
            code = None if ok else outcome["error"]["code"]
            events.append(
                ToolEvent(message.name or "?", arguments, ok, outcome.get("result"), error, code)
            )
        else:
            # The framework refused the call before our code ran (bad arguments, unknown tool).
            error = clean_framework_error(message_text(message.content))
            events.append(
                ToolEvent(message.name or "?", arguments, False, None, error, "invalid_call")
            )
    return events


def evidence_texts(messages: list[BaseMessage]) -> list[str]:
    """The text the model was shown by tools that REALLY ran our code.

    Only these count as evidence. A call the framework rejected (bad arguments, unknown
    tool) never touched the database, so it proves nothing and must not let an answer pass.

    Args:
        messages: The messages of a finished (or stopped) graph run.

    Returns:
        One text per tool call that really ran our code.
    """
    return [
        message_text(m.content)
        for m in messages
        if isinstance(m, ToolMessage) and isinstance(m.artifact, dict) and "ok" in m.artifact
    ]


def _flatten(result: Any) -> list[dict]:
    """Reduce a tool result to the list of records inside it.

    Args:
        result: A tool's ``result``: a list of records, one record, or a proposal.

    Returns:
        The records (a proposal contributes its ``change``).
    """
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        # A proposal returns {"change": ..., "preview": ...}; the change is the record.
        return [result["change"]] if isinstance(result.get("change"), dict) else [result]
    return []


def collect_records(events: list[ToolEvent]) -> list[dict]:
    """Collect the distinct records the tools returned (shown beside the answer as evidence).

    Args:
        events: The tool runs of one chat message.

    Returns:
        Each record once, in the order first seen. Failed tool runs contribute nothing.
    """
    records: list[dict] = []
    seen: set[str] = set()
    for event in events:
        if not event.ok:
            continue
        for item in _flatten(event.result):
            key = json.dumps(item, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                records.append(item)
    return records


def tool_trace(events: list[ToolEvent]) -> list[dict]:
    """Describe every tool that ran, briefly and safely (the "tool trace" shown to the user).

    Args:
        events: The tool runs of one chat message.

    Returns:
        One entry per run with its ``name``, ``arguments``, ``ok`` flag and ``error``.
    """
    return [
        {"name": e.name, "arguments": e.arguments, "ok": e.ok, "error": e.error} for e in events
    ]
