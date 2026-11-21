"""Turnier: Turnier, Stand, Klasse und Wettbewerb.

Revision ID: 0002_turnier
Revises: 0001
Create Date: 2026-11-21 23:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_turnier"
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
        "tournament",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("organizer", sa.String(length=200), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("template", sa.String(length=30), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'closed')", name=op.f("ck_tournament_status")
        ),
        sa.CheckConstraint(
            "template IN ('open', 'club_championship', 'custom')",
            name=op.f("ck_tournament_template"),
        ),
        sa.CheckConstraint("date_to >= date_from", name=op.f("ck_tournament_dates")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tournament")),
    )
    op.create_table(
        "range",
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("lane_count", sa.Integer(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("lane_count >= 1", name=op.f("ck_range_lane_count")),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournament.id"],
            name=op.f("fk_range_tournament_id_tournament"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_range")),
    )
    op.create_index(op.f("ix_range_tournament_id"), "range", ["tournament_id"], unique=False)
    op.create_table(
        "tournament_class",
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("short", sa.String(length=40), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("merge_into_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["merge_into_id"],
            ["tournament_class.id"],
            name=op.f("fk_tournament_class_merge_into_id_tournament_class"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournament.id"],
            name=op.f("fk_tournament_class_tournament_id_tournament"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tournament_class")),
        sa.UniqueConstraint(
            "tournament_id", "code", name=op.f("uq_tournament_class_tournament_id")
        ),
    )
    op.create_index(
        op.f("ix_tournament_class_tournament_id"),
        "tournament_class",
        ["tournament_id"],
        unique=False,
    )
    op.create_table(
        "competition",
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("range_id", sa.Uuid(), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("catalog_federation", sa.String(length=80), nullable=True),
        sa.Column("catalog_code", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("capture_mode", sa.String(length=20), nullable=False),
        sa.Column("multi_start", sa.Boolean(), nullable=False),
        sa.Column("max_starts", sa.Integer(), nullable=False),
        sa.Column("multi_start_rule", sa.String(length=20), nullable=False),
        sa.Column("fee_first_cents", sa.Integer(), nullable=False),
        sa.Column("fee_repeat_cents", sa.Integer(), nullable=False),
        sa.Column("class_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("combined_ranking", sa.Boolean(), nullable=False),
        sa.Column("planning", sa.String(length=20), nullable=False),
        sa.Column("heat_minutes", sa.Integer(), nullable=True),
        sa.Column("changeover_minutes", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "capture_mode IN ('shot', 'series')", name=op.f("ck_competition_capture_mode")
        ),
        sa.CheckConstraint(
            "multi_start_rule IN ('best', 'first', 'all')",
            name=op.f("ck_competition_multi_start_rule"),
        ),
        sa.CheckConstraint(
            "planning IN ('queue', 'schedule')", name=op.f("ck_competition_planning")
        ),
        sa.CheckConstraint("max_starts >= 1", name=op.f("ck_competition_max_starts")),
        sa.CheckConstraint(
            "fee_first_cents >= 0 AND fee_repeat_cents >= 0", name=op.f("ck_competition_fees")
        ),
        sa.CheckConstraint(
            "heat_minutes IS NULL OR heat_minutes >= 1", name=op.f("ck_competition_heat_minutes")
        ),
        sa.CheckConstraint(
            "changeover_minutes >= 0", name=op.f("ck_competition_changeover_minutes")
        ),
        sa.ForeignKeyConstraint(
            ["range_id"],
            ["range.id"],
            name=op.f("fk_competition_range_id_range"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournament.id"],
            name=op.f("fk_competition_tournament_id_tournament"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competition")),
    )
    op.create_index(op.f("ix_competition_range_id"), "competition", ["range_id"], unique=False)
    op.create_index(
        op.f("ix_competition_tournament_id"), "competition", ["tournament_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_competition_tournament_id"), table_name="competition")
    op.drop_index(op.f("ix_competition_range_id"), table_name="competition")
    op.drop_table("competition")
    op.drop_index(op.f("ix_tournament_class_tournament_id"), table_name="tournament_class")
    op.drop_table("tournament_class")
    op.drop_index(op.f("ix_range_tournament_id"), table_name="range")
    op.drop_table("range")
    op.drop_table("tournament")
