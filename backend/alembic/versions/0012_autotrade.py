"""simulated autotrade config

Revision ID: 0012_autotrade
Revises: 0011_telegram_link
Create Date: 2026-11-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_autotrade"
down_revision = "0011_telegram_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autotrade_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_position_usd", sa.Float(), nullable=False, server_default="100"),
        sa.Column("daily_cap_usd", sa.Float(), nullable=False, server_default="500"),
        sa.Column("min_confidence", sa.Float(), nullable=False, server_default="0.9"),
        sa.Column("tp_pct", sa.Float(), nullable=False, server_default="50"),
        sa.Column("stop_pct", sa.Float(), nullable=False, server_default="25"),
        sa.Column("chains", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("day_key", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("day_spent_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_autotrade_config_user"),
    )


def downgrade() -> None:
    op.drop_table("autotrade_config")
