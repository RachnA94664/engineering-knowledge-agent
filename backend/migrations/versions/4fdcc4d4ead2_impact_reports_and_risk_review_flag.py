"""impact reports and risk review flag

Revision ID: 4fdcc4d4ead2
Revises: 13cf4b0d8c97
Create Date: 2026-10-04 15:39:46.341609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4fdcc4d4ead2'
down_revision: Union[str, Sequence[str], None] = '13cf4b0d8c97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the impact_reports table and the risk review flag."""
    op.create_table(
        "impact_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("requirement_id", sa.String(length=16), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("report", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("level IN ('low', 'medium', 'high')", name="ck_impact_reports_level"),
        sa.ForeignKeyConstraint(["change_id"], ["pending_changes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("change_id", name="uq_impact_reports_change_id"),
    )
    op.create_index("ix_impact_reports_requirement_id", "impact_reports", ["requirement_id"])

    # A plain constant default makes SQLite do a simple ALTER TABLE ... ADD COLUMN.
    # (A SQL-expression default such as sa.text("0") makes Alembic rebuild the whole table,
    # and dropping risk_items fails because other tables reference it.)
    op.add_column(
        "risk_items",
        sa.Column("needs_review", sa.Boolean(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    # SQLite can drop a plain column natively; no table rebuild is needed.
    op.drop_column("risk_items", "needs_review")
    op.drop_index("ix_impact_reports_requirement_id", table_name="impact_reports")
    op.drop_table("impact_reports")
