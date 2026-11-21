"""Sicherung: globale Einstellungen (setting) und Protokoll der Sicherungsläufe (backup_run).

Revision ID: 0005_backup
Revises: 0001
Create Date: 2026-11-21 23:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_backup"
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
        "setting",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_setting")),
        sa.UniqueConstraint("key", name=op.f("uq_setting_key")),
    )
    op.create_table(
        "backup_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("target", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_run")),
    )
    op.create_index(op.f("ix_backup_run_started_at"), "backup_run", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_backup_run_started_at"), table_name="backup_run")
    op.drop_table("backup_run")
    op.drop_table("setting")
