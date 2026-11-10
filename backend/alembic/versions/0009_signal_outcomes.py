"""signal_outcomes (T3 — обучение на исходах)

Revision ID: 0009_signal_outcomes
Revises: 0008_social
Create Date: 2026-11-10
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_signal_outcomes"
down_revision = "0008_social"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chain", sa.String(length=32), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("features", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("horizon_minutes", sa.Integer(), nullable=False),
        sa.Column("label", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_signal_outcomes_chain_addr", "signal_outcomes", ["chain", "address"]
    )
    op.create_index("ix_signal_outcomes_label", "signal_outcomes", ["label"])
    op.create_index(
        "ix_signal_outcomes_created_at", "signal_outcomes", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_signal_outcomes_created_at", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_label", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_chain_addr", table_name="signal_outcomes")
    op.drop_table("signal_outcomes")
