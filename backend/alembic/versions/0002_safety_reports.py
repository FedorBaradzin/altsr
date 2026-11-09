"""safety_reports

Revision ID: 0002_safety_reports
Revises: 0001_init
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_safety_reports"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "safety_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("chain", sa.String(length=32), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=8), nullable=False),
        sa.Column("red_flags", sa.Text(), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("sources", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_id", name="uq_safety_token"),
    )
    op.create_index("ix_safety_token_id", "safety_reports", ["token_id"])
    op.create_index("ix_safety_verdict", "safety_reports", ["verdict"])
    op.create_index("ix_safety_chain_address", "safety_reports", ["chain", "address"])


def downgrade() -> None:
    op.drop_index("ix_safety_chain_address", table_name="safety_reports")
    op.drop_index("ix_safety_verdict", table_name="safety_reports")
    op.drop_index("ix_safety_token_id", table_name="safety_reports")
    op.drop_table("safety_reports")
