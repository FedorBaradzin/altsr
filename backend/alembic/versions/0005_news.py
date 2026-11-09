"""news_items

Revision ID: 0005_news
Revises: 0004_paper
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_news"
down_revision = "0004_paper"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chain", sa.String(length=32), nullable=True),
        sa.Column("address", sa.String(length=128), nullable=True),
        sa.Column("classified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("catalyst", sa.String(length=32), nullable=True),
        sa.Column("sentiment", sa.Float(), nullable=True),
        sa.Column("urgency", sa.String(length=8), nullable=True),
        sa.Column("credibility", sa.String(length=24), nullable=True),
        sa.Column("model", sa.String(length=48), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("url", name="uq_news_url"),
    )
    op.create_index("ix_news_created_at", "news_items", ["created_at"])
    op.create_index("ix_news_urgency", "news_items", ["urgency"])
    op.create_index("ix_news_chain_address", "news_items", ["chain", "address"])


def downgrade() -> None:
    op.drop_index("ix_news_chain_address", table_name="news_items")
    op.drop_index("ix_news_urgency", table_name="news_items")
    op.drop_index("ix_news_created_at", table_name="news_items")
    op.drop_table("news_items")
