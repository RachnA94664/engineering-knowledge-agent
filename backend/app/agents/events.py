"""Read the tool results out of a finished (or stopped) graph run.

The graph state holds LangChain messages. Every tool run leaves a ToolMessage whose
`artifact` is the raw outcome ({"ok": ..., "result" | "error": ...}). From those we build
the three things the user and the safety checks need: the evidence, the trace, the records.
"""

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


def message_text(content: Any) -> str:
    """A message's text, whether the provider returned a string or a list of parts."""
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


def tool_events(messages: list[BaseMessage]) -> list[ToolEvent]:
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
            events.append(
                ToolEvent(message.name or "?", arguments, ok, outcome.get("result"), error)
            )
        else:
            # The framework refused the call before our code ran (bad arguments, unknown tool).
            events.append(
                ToolEvent(
                    message.name or "?", arguments, False, None, message_text(message.content)
                )
            )
    return events


def evidence_texts(messages: list[BaseMessage]) -> list[str]:
    """The text the model was shown by tools that REALLY ran our code.

    Only these count as evidence. A call the framework rejected (bad arguments, unknown
    tool) never touched the database, so it proves nothing and must not let an answer pass.
    """
    return [
        message_text(m.content)
        for m in messages
        if isinstance(m, ToolMessage) and isinstance(m.artifact, dict) and "ok" in m.artifact
    ]


def _flatten(result: Any) -> list[dict]:
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        # A proposal returns {"change": ..., "preview": ...}; the change is the record.
        return [result["change"]] if isinstance(result.get("change"), dict) else [result]
    return []


def collect_records(events: list[ToolEvent]) -> list[dict]:
    """The distinct records the tools returned (the evidence shown beside the answer)."""
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
    """A short, safe description of every tool that ran."""
    return [
        {"name": e.name, "arguments": e.arguments, "ok": e.ok, "error": e.error} for e in events
    ]
