"""Anmeldung und Rechte: Rolle, Person, Gerät, Sitzung, Kopplungscode, Audit-Protokoll.

Revision ID: 0004_auth
Revises: 0001
Create Date: 2026-11-21 23:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_auth"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "role",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_role"),
        sa.UniqueConstraint("name", name="uq_role_name"),
    )

    op.create_table(
        "user_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("pin_hash", sa.Text(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["role_id"], ["role.id"], name="fk_user_account_role_id_role", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_account"),
        sa.UniqueConstraint("name", name="uq_user_account_name"),
    )
    op.create_index("ix_user_account_role_id", "user_account", ["role_id"])

    op.create_table(
        "device",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("paired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("default_role_id", sa.Uuid(), nullable=True),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["default_role_id"],
            ["role.id"],
            name="fk_device_default_role_id_role",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device"),
        sa.UniqueConstraint("token_hash", name="uq_device_token_hash"),
    )
    op.create_index("ix_device_default_role_id", "device", ["default_role_id"])

    op.create_table(
        "session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["device_id"], ["device.id"], name="fk_session_device_id_device", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name="fk_session_user_id_user_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session"),
        sa.UniqueConstraint("token_hash", name="uq_session_token_hash"),
    )
    op.create_index("ix_session_device_id", "session", ["device_id"])
    op.create_index("ix_session_user_id", "session", ["user_id"])

    op.create_table(
        "pairing_code",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=True),
        sa.Column("default_role_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["default_role_id"],
            ["role.id"],
            name="fk_pairing_code_default_role_id_role",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pairing_code"),
        sa.UniqueConstraint("code_hash", name="uq_pairing_code_code_hash"),
    )
    op.create_index("ix_pairing_code_default_role_id", "pairing_code", ["default_role_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_pairing_code_default_role_id", table_name="pairing_code")
    op.drop_table("pairing_code")
    op.drop_index("ix_session_user_id", table_name="session")
    op.drop_index("ix_session_device_id", table_name="session")
    op.drop_table("session")
    op.drop_index("ix_device_default_role_id", table_name="device")
    op.drop_table("device")
    op.drop_index("ix_user_account_role_id", table_name="user_account")
    op.drop_table("user_account")
    op.drop_table("role")
