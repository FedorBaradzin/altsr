"""telegram linking: users.tg_chat_id + telegram_link_codes

Revision ID: 0011_telegram_link
Revises: 0010_user_paper
Create Date: 2026-11-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_telegram_link"
down_revision = "0010_user_paper"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tg_chat_id", sa.String(length=32), nullable=True))
    op.create_table(
        "telegram_link_codes",
        sa.Column("code", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("telegram_link_codes")
    op.drop_column("users", "tg_chat_id")
