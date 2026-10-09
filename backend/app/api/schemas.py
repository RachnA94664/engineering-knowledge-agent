"""The API contract: the exact shape of every request and response.

Input models use `extra="forbid"`: unknown fields are rejected, so a client can
never sneak in something like `source` or `version`.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictIn(BaseModel):
    """Base of every request body: unknown fields are rejected, never ignored."""

    model_config = ConfigDict(extra="forbid")


# ---------- requests ----------


class ProposeChangeIn(StrictIn):
    """Propose a change to a requirement. Nothing is applied until a person confirms it."""

    requirement_id: str = Field(examples=["REQ-007"])
    patch: dict[str, Any] = Field(examples=[{"status": "implemented"}])
    proposed_by: str = Field(min_length=1, max_length=64, examples=["rachna"])


class ActorIn(StrictIn):
    """Who is confirming, rejecting or reviewing (written to the audit log)."""

    actor: str = Field(min_length=1, max_length=64, examples=["rachna"])


# ---------- responses ----------


class RequirementOut(BaseModel):
    """A requirement: something the product must do."""

    id: str
    title: str
    description: str
    priority: str
    status: str
    version: int
    created_at: str | None
    updated_at: str | None


class TestCaseOut(BaseModel):
    """A test case that verifies one requirement."""

    __test__ = False  # not a pytest class, despite the name
    id: str
    requirement_id: str
    title: str
    steps: str
    expected_result: str
    status: str


class RiskOut(BaseModel):
    """A risk item, with its derived score and level."""

    id: str
    title: str
    description: str
    severity: int
    likelihood: int
    status: str
    score: int = Field(description="severity x likelihood (derived, never stored)")
    level: str = Field(description="low, medium or high (derived, never stored)")
    needs_review: bool = Field(
        description="set automatically when a confirmed change may affect this risk; "
        "cleared by a person via POST /risks/{id}/reviewed"
    )


class ChangeOut(BaseModel):
    """A proposed change and where it stands (pending, applied, rejected or expired)."""

    id: int
    entity_type: str
    entity_id: str
    patch: dict[str, Any]
    base_version: int
    proposed_by: str
    status: str
    created_at: str | None
    resolved_at: str | None


class ProposeOut(BaseModel):
    """A saved proposal and a preview of what it would change."""

    change: ChangeOut
    preview: dict[str, dict[str, Any]] = Field(description="field -> {old, new}")


class ResetTestOut(BaseModel):
    """A passing test case that an impact analysis reset to ``not_run``."""

    id: str
    title: str
    old_status: str
    new_status: str


class FailingTestOut(BaseModel):
    """A linked test case that was already failing or blocked."""

    id: str
    title: str
    status: str


class RiskToFlagOut(BaseModel):
    """A linked risk that an impact analysis flagged for review."""

    id: str
    title: str
    score: int
    level: str
    status: str
    already_flagged: bool


class ImpactReportOut(BaseModel):
    """What a confirmed change affected. Written by rules, never by the AI."""

    id: int
    change_id: int
    created_at: str | None
    requirement_id: str
    level: str = Field(description="low, medium or high")
    changed_fields: dict[str, dict[str, Any]] = Field(description="field -> {old, new}")
    tests_to_reset: list[ResetTestOut] = Field(description="passing tests reset to not_run")
    tests_failing: list[FailingTestOut] = Field(description="linked tests that fail or are blocked")
    risks_to_flag: list[RiskToFlagOut] = Field(description="linked risks flagged for review")
    warnings: list[str]
    summary: str = Field(description="a plain sentence describing the impact")


class ConfirmOut(BaseModel):
    """The result of confirming a change (the same result if it is confirmed twice)."""

    change: ChangeOut
    already_applied: bool
    requirement: RequirementOut | None = None
    impact: ImpactReportOut | None = Field(
        default=None, description="the automatic impact analysis of this change"
    )


class RejectOut(BaseModel):
    """The result of rejecting a change (the same result if it is rejected twice)."""

    change: ChangeOut
    already_rejected: bool


class AuditOut(BaseModel):
    """One audit-log entry: who changed what, when, and the values before and after."""

    id: int
    ts: str | None
    actor: str
    source: str
    entity_type: str
    entity_id: str
    action: str
    old_value: Any | None
    new_value: Any | None
    request_id: str | None


class ChatIn(StrictIn):
    """A message to the agents, in plain English (at most 1000 characters)."""

    message: str = Field(max_length=1000, examples=["Which requirements have no test cases?"])


class ToolCallOut(BaseModel):
    """One tool an agent ran: its name, its arguments and whether it succeeded."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    error: str | None = None


class PendingChangeOut(BaseModel):
    """A proposal the update agent saved, with its preview."""

    change: ChangeOut
    preview: dict[str, dict[str, Any]]


class ChatOut(BaseModel):
    """The agents' reply: the answer, the evidence behind it and any proposals."""

    answer: str
    intent: str = Field(description="query, update, out_of_scope or refused")
    grounded: bool = Field(description="True if the answer is backed by database results")
    refused: bool = Field(description="True if the system declined to act")
    records: list[dict[str, Any]] = Field(description="the database records behind the answer")
    tool_calls: list[ToolCallOut] = Field(description="every tool the agent ran")
    pending_changes: list[PendingChangeOut] = Field(
        description="proposals saved by the Update Agent; nothing is applied until confirmed"
    )


class HealthOut(BaseModel):
    """Whether the API is up and its database reachable and up to date."""

    status: str
    database: str


class ErrorDetail(BaseModel):
    """What went wrong: a stable ``code``, a readable ``message`` and optional ``details``."""

    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorOut(BaseModel):
    """The one shape every error response has."""

    error: ErrorDetail
