"""init tokens

Revision ID: 0001_init
Revises:
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chain", sa.String(length=32), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("liquidity_usd", sa.Float(), nullable=True),
        sa.Column("fdv", sa.Float(), nullable=True),
        sa.Column("pair_address", sa.String(length=128), nullable=True),
        sa.Column("dex", sa.String(length=64), nullable=True),
        sa.Column("socials", sa.String(length=2048), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_count", sa.BigInteger(), nullable=False, server_default="1"),
        sa.UniqueConstraint("chain", "address", name="uq_tokens_chain_address"),
    )
    op.create_index("ix_tokens_chain_address", "tokens", ["chain", "address"])
    op.create_index("ix_tokens_discovered_at", "tokens", ["discovered_at"])
    op.create_index("ix_tokens_chain", "tokens", ["chain"])


def downgrade() -> None:
    op.drop_index("ix_tokens_chain", table_name="tokens")
    op.drop_index("ix_tokens_discovered_at", table_name="tokens")
    op.drop_index("ix_tokens_chain_address", table_name="tokens")
    op.drop_table("tokens")
