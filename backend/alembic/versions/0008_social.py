"""articles.social_posted

Revision ID: 0008_social
Revises: 0007_accounts
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_social"
down_revision = "0007_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("social_posted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("articles", "social_posted")
