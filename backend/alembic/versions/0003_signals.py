"""signals

Revision ID: 0003_signals
Revises: 0002_safety_reports
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_signals"
down_revision = "0002_safety_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("chain", sa.String(length=32), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False, server_default="BUY"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reasons", sa.Text(), nullable=True),
        sa.Column("venues", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_id", name="uq_signal_token"),
    )
    op.create_index("ix_signal_token_id", "signals", ["token_id"])
    op.create_index("ix_signal_created_at", "signals", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_signal_created_at", table_name="signals")
    op.drop_index("ix_signal_token_id", table_name="signals")
    op.drop_table("signals")
