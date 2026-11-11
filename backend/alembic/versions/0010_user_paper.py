"""per-user paper account

Revision ID: 0010_user_paper
Revises: 0009_signal_outcomes
Create Date: 2026-11-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_user_paper"
down_revision = "0009_signal_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_paper_account",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("start_balance", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_user_paper_account_user"),
    )

    op.create_table(
        "user_paper_positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("chain", sa.String(length=32), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("bias", sa.Float(), nullable=False),
        sa.Column("seed", sa.Float(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["user_paper_account.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_paper_positions_account", "user_paper_positions", ["account_id"])

    op.create_table(
        "user_paper_trades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("chain", sa.String(length=32), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("exit_value", sa.Float(), nullable=False),
        sa.Column("pnl_usd", sa.Float(), nullable=False),
        sa.Column("pnl_pct", sa.Float(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["user_paper_account.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_paper_trades_account", "user_paper_trades", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_user_paper_trades_account", table_name="user_paper_trades")
    op.drop_table("user_paper_trades")
    op.drop_index("ix_user_paper_positions_account", table_name="user_paper_positions")
    op.drop_table("user_paper_positions")
    op.drop_table("user_paper_account")
