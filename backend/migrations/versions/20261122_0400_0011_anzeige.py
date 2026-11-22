"""Anzeige: Tabelle display (Anzeigen mit Szenen, Turnier und zugewiesenem Gerät).

Revision ID: 0011_anzeige
Revises: 0010_merge
Create Date: 2026-11-22 04:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_anzeige"
down_revision: str | Sequence[str] | None = "0010_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "display",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournament.id"],
            name=op.f("fk_display_tournament_id_tournament"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["device.id"],
            name=op.f("fk_display_device_id_device"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_display")),
        sa.UniqueConstraint("name", name=op.f("uq_display_name")),
        sa.UniqueConstraint("device_id", name=op.f("uq_display_device_id")),
    )
    op.create_index(op.f("ix_display_tournament_id"), "display", ["tournament_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_display_tournament_id"), table_name="display")
    op.drop_table("display")
