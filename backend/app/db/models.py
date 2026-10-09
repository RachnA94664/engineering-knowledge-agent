"""SQLAlchemy models = the database schema.

Every rule that can be enforced by the database is enforced here (primary
keys, foreign keys, CHECK constraints), as a second line of defence behind the
domain and service layers.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.domain import enums


class UTCDateTime(TypeDecorator):
    """A timestamp that is ALWAYS stored and returned as UTC with its timezone attached.

    SQLite has no timezone support: it silently drops the timezone when saving, so a value read
    back looked different from the one just saved ("...+00:00" vs no suffix). This type stores
    UTC and puts the timezone back on every read, so all timestamps look the same everywhere.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Prepare a timestamp for storing: it must carry a timezone and is saved as UTC.

        Args:
            value: The timestamp to store, or None.
            dialect: The database dialect (unused; part of SQLAlchemy's interface).

        Returns:
            The timestamp converted to UTC, or None.

        Raises:
            ValueError: If the timestamp has no timezone attached.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("timestamps must carry a timezone (use datetime.now(UTC))")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        """Rebuild a stored timestamp: SQLite forgets the timezone, so UTC is put back.

        Args:
            value: The timestamp as read from the database, or None.
            dialect: The database dialect (unused; part of SQLAlchemy's interface).

        Returns:
            A timezone-aware UTC timestamp, or None.
        """
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _in(column: str, values: tuple[str, ...]) -> str:
    """Build ``column IN ('a','b')`` for a CHECK constraint.

    Args:
        column: The column name.
        values: The allowed values.

    Returns:
        The SQL text of the condition.
    """
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """The base class of every table class below."""


class Requirement(Base):
    """A requirement: something the product must do (``REQ-001``).

    ``version`` goes up on every change and is used for optimistic locking: a proposed change
    remembers the version it was based on and cannot be applied if the requirement moved on.
    """

    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint(f"id GLOB '{enums.REQ_ID_GLOB}'", name="ck_requirements_id_format"),
        CheckConstraint(_in("priority", enums.PRIORITIES), name="ck_requirements_priority"),
        CheckConstraint(_in("status", enums.REQUIREMENT_STATUSES), name="ck_requirements_status"),
        CheckConstraint("length(trim(title)) > 0", name="ck_requirements_title_not_blank"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic locking
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="requirement")
    risk_links: Mapped[list["RequirementRisk"]] = relationship(back_populates="requirement")


class TestCase(Base):
    """A test case that verifies exactly one requirement (``TC-001``)."""

    __tablename__ = "test_cases"
    __test__ = False  # stop pytest treating this class as a test class
    __table_args__ = (
        CheckConstraint(f"id GLOB '{enums.TC_ID_GLOB}'", name="ck_test_cases_id_format"),
        CheckConstraint(_in("status", enums.TEST_STATUSES), name="ck_test_cases_status"),
        CheckConstraint("length(trim(title)) > 0", name="ck_test_cases_title_not_blank"),
        Index("ix_test_cases_requirement_id", "requirement_id"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200))
    steps: Mapped[str] = mapped_column(Text, default="")
    expected_result: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="not_run")

    requirement: Mapped[Requirement] = relationship(back_populates="test_cases")


class RiskItem(Base):
    """Risk score and level are NOT stored: they are derived in the domain layer."""

    __tablename__ = "risk_items"
    __table_args__ = (
        CheckConstraint(f"id GLOB '{enums.RISK_ID_GLOB}'", name="ck_risk_items_id_format"),
        CheckConstraint("severity BETWEEN 1 AND 5", name="ck_risk_items_severity"),
        CheckConstraint("likelihood BETWEEN 1 AND 5", name="ck_risk_items_likelihood"),
        CheckConstraint(_in("status", enums.RISK_STATUSES), name="ck_risk_items_status"),
        CheckConstraint("length(trim(title)) > 0", name="ck_risk_items_title_not_blank"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[int] = mapped_column(Integer)
    likelihood: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="open")
    # Set automatically when a confirmed requirement change may affect this risk; a person
    # clears it after reviewing the risk.
    needs_review: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    requirement_links: Mapped[list["RequirementRisk"]] = relationship(back_populates="risk")


class RequirementRisk(Base):
    """Many-to-many join table between requirements and risk items."""

    __tablename__ = "requirement_risks"
    __table_args__ = (Index("ix_requirement_risks_risk_id", "risk_id"),)

    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("requirements.id", ondelete="RESTRICT"), primary_key=True
    )
    risk_id: Mapped[str] = mapped_column(
        ForeignKey("risk_items.id", ondelete="RESTRICT"), primary_key=True
    )

    requirement: Mapped[Requirement] = relationship(back_populates="risk_links")
    risk: Mapped[RiskItem] = relationship(back_populates="requirement_links")


class AuditLog(Base):
    """Append-only history of every modification (triggers added in Phase 4)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(_in("source", enums.AUDIT_SOURCES), name="ck_audit_log_source"),
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    actor: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(32))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON text
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON text
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PendingChange(Base):
    """A proposed update waiting for a human to confirm or reject it."""

    __tablename__ = "pending_changes"
    __table_args__ = (
        CheckConstraint(_in("status", enums.PENDING_STATUSES), name="ck_pending_changes_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(32))
    proposed_patch: Mapped[str] = mapped_column(Text)  # JSON text
    base_version: Mapped[int] = mapped_column(Integer)
    proposed_by: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ImpactReport(Base):
    """The result of the automatic impact analysis run when a change is confirmed.

    One report per applied change (`change_id` is unique), so confirming twice never makes a
    second one. The full detail is stored as JSON text; `level` is also a column so it can be
    filtered and is protected by a CHECK constraint.
    """

    __tablename__ = "impact_reports"
    __table_args__ = (
        CheckConstraint(_in("level", enums.IMPACT_LEVELS), name="ck_impact_reports_level"),
        UniqueConstraint("change_id", name="uq_impact_reports_change_id"),
        Index("ix_impact_reports_requirement_id", "requirement_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id", ondelete="RESTRICT"))
    change_id: Mapped[int] = mapped_column(ForeignKey("pending_changes.id", ondelete="RESTRICT"))
    level: Mapped[str] = mapped_column(String(16))
    report: Mapped[str] = mapped_column(Text)  # JSON text
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
