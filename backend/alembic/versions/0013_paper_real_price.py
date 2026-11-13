"""paper positions: real entry price + token address for live DEX valuation

Revision ID: 0013_paper_real_price
Revises: 0012_autotrade
Create Date: 2026-11-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_paper_real_price"
down_revision = "0012_autotrade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_paper_positions", sa.Column("entry_price", sa.Float(), nullable=True))
    op.add_column("user_paper_positions", sa.Column("address", sa.String(length=128), nullable=True))
    op.add_column("user_paper_positions", sa.Column("pair_address", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("user_paper_positions", "pair_address")
    op.drop_column("user_paper_positions", "address")
    op.drop_column("user_paper_positions", "entry_price")
