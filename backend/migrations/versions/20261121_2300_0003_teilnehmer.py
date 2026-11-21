"""Teilnehmer: Verein und Person (Name und Mitgliedsnummer verschlüsselt).

Revision ID: 0003_teilnehmer
Revises: 0001
Create Date: 2026-11-21 23:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_teilnehmer"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "club",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("short", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_club")),
    )
    op.create_index("uq_club_name_ci", "club", [sa.text("lower(name)")], unique=True)

    op.create_table(
        "person",
        sa.Column("id", sa.Uuid(), nullable=False),
        # AES-256-GCM, siehe app/core/crypto.py.
        sa.Column("name_enc", sa.LargeBinary(), nullable=False),
        sa.Column("member_no_enc", sa.LargeBinary(), nullable=True),
        sa.Column("club_id", sa.Uuid(), nullable=True),
        sa.Column("display_mode", sa.String(length=10), nullable=False),
        sa.Column("show_club", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "display_mode IN ('full', 'short', 'hidden')",
            name=op.f("ck_person_display_mode"),
        ),
        sa.ForeignKeyConstraint(["club_id"], ["club.id"], name=op.f("fk_person_club_id_club")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person")),
    )
    op.create_index(op.f("ix_person_club_id"), "person", ["club_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_person_club_id"), table_name="person")
    op.drop_table("person")
    op.drop_index("uq_club_name_ci", table_name="club")
    op.drop_table("club")
