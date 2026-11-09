"""paper account + positions

Revision ID: 0004_paper
Revises: 0003_signals
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_paper"
down_revision = "0003_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_account",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("start_balance", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "paper_positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("chain", sa.String(length=32), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False, server_default="open"),
        sa.Column("size_usd", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("peak_price", sa.Float(), nullable=False),
        sa.Column("last_price", sa.Float(), nullable=False),
        sa.Column("remaining_fraction", sa.Float(), nullable=False, server_default="1"),
        sa.Column("tp_taken", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("realized_pnl_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("exit_reason", sa.String(length=64), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_high_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_id", name="uq_paper_position_token"),
    )
    op.create_index("ix_paper_positions_status", "paper_positions", ["status"])
    op.create_index("ix_paper_positions_token_id", "paper_positions", ["token_id"])


def downgrade() -> None:
    op.drop_index("ix_paper_positions_token_id", table_name="paper_positions")
    op.drop_index("ix_paper_positions_status", table_name="paper_positions")
    op.drop_table("paper_positions")
    op.drop_table("paper_account")
