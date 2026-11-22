"""Turnier: Revisionen der wertungsrelevanten Felder eines Wettbewerbs, Ausschreibung.

Neue Tabelle `competition_revision` und Spalte `competition.definition_revision`. Vorhandene
Wettbewerbe bekommen ihren aktuellen Stand als Revision 1. Neue Spalte `tournament.announcement`
(leer bei vorhandenen Turnieren: Dann gilt die Standardgliederung der Vorlage).

Revision ID: 0008_turnier_versionen
Revises: 0006_merge
Create Date: 2026-11-22 01:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_turnier_versionen"
down_revision: str | Sequence[str] | None = "0006_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tournament",
        sa.Column("announcement", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "competition",
        sa.Column("definition_revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_table(
        "competition_revision",
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("capture_mode", sa.String(length=20), nullable=False),
        sa.Column("multi_start", sa.Boolean(), nullable=False),
        sa.Column("max_starts", sa.Integer(), nullable=False),
        sa.Column("multi_start_rule", sa.String(length=20), nullable=False),
        sa.Column("combined_ranking", sa.Boolean(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_competition_revision_revision")),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["competition.id"],
            name=op.f("fk_competition_revision_competition_id_competition"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competition_revision")),
        sa.UniqueConstraint(
            "competition_id", "revision", name=op.f("uq_competition_revision_competition_id")
        ),
    )
    op.create_index(
        op.f("ix_competition_revision_competition_id"),
        "competition_revision",
        ["competition_id"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO competition_revision (
            id, competition_id, revision, definition, capture_mode, multi_start, max_starts,
            multi_start_rule, combined_ranking
        )
        SELECT gen_random_uuid(), id, 1, definition, capture_mode, multi_start, max_starts,
               multi_start_rule, combined_ranking
        FROM competition
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_competition_revision_competition_id"), table_name="competition_revision")
    op.drop_table("competition_revision")
    op.drop_column("competition", "definition_revision")
    op.drop_column("tournament", "announcement")
