"""users + payments

Revision ID: 0007_accounts
Revises: 0006_articles
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_accounts"
down_revision = "0006_articles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("auth_method", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=True),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("tier", sa.String(length=16), nullable=False, server_default="free"),
        sa.Column("tier_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("auth_method", "subject", name="uq_user_identity"),
    )
    op.create_index("ix_users_auth_subject", "users", ["auth_method", "subject"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False, server_default="nowpayments"),
        sa.Column("invoice_id", sa.String(length=64), nullable=True),
        sa.Column("payment_id", sa.String(length=64), nullable=True),
        sa.Column("amount_usd", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="waiting"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_invoice", "payments", ["invoice_id"])
    op.create_index("ix_payments_payment_id", "payments", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_payment_id", table_name="payments")
    op.drop_index("ix_payments_invoice", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_users_auth_subject", table_name="users")
    op.drop_table("users")
