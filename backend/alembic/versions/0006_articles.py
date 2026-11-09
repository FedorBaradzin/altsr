"""articles

Revision ID: 0006_articles
Revises: 0005_news
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_articles"
down_revision = "0005_news"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False, server_default="en"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("meta_description", sa.String(length=320), nullable=False),
        sa.Column("keywords", sa.String(length=400), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("source_name", sa.String(length=120), nullable=True),
        sa.Column("news_id", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=48), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="published"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["news_id"], ["news_items.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("slug", name="uq_article_slug"),
    )
    op.create_index("ix_article_published_at", "articles", ["published_at"])
    op.create_index("ix_article_news_id", "articles", ["news_id"])


def downgrade() -> None:
    op.drop_index("ix_article_news_id", table_name="articles")
    op.drop_index("ix_article_published_at", table_name="articles")
    op.drop_table("articles")
