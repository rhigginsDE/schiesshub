"""Starts: Anmeldung (entry), Durchgang (heat) und Start (start).

Revision ID: 0007_starts
Revises: 0006_merge
Create Date: 2026-11-22 01:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_starts"
down_revision: str | Sequence[str] | None = "0006_merge"
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
        "entry",
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("class_id", sa.Uuid(), nullable=False),
        sa.Column("start_number", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("start_number >= 1", name=op.f("ck_entry_start_number")),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournament.id"],
            name=op.f("fk_entry_tournament_id_tournament"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["person.id"], name=op.f("fk_entry_person_id_person")
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["tournament_class.id"], name=op.f("fk_entry_class_id_tournament_class")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entry")),
        sa.UniqueConstraint("tournament_id", "start_number", name="uq_entry_start_number"),
        sa.UniqueConstraint("tournament_id", "person_id", name="uq_entry_person"),
    )
    op.create_index(op.f("ix_entry_tournament_id"), "entry", ["tournament_id"], unique=False)
    op.create_index(op.f("ix_entry_person_id"), "entry", ["person_id"], unique=False)
    op.create_index(op.f("ix_entry_class_id"), "entry", ["class_id"], unique=False)

    op.create_table(
        "heat",
        sa.Column("range_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("number >= 1", name=op.f("ck_heat_number")),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_heat_times")),
        sa.ForeignKeyConstraint(
            ["range_id"], ["range.id"], name=op.f("fk_heat_range_id_range"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heat")),
        sa.UniqueConstraint("range_id", "number", name="uq_heat_number"),
    )
    op.create_index(op.f("ix_heat_range_id"), "heat", ["range_id"], unique=False)

    op.create_table(
        "start",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("fee_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("abort_reason", sa.String(length=10), nullable=True),
        sa.Column("queue_position", sa.Integer(), nullable=True),
        sa.Column("heat_id", sa.Uuid(), nullable=True),
        sa.Column("lane", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('registered', 'called', 'captured', 'final', 'aborted')",
            name=op.f("ck_start_status"),
        ),
        sa.CheckConstraint(
            "abort_reason IS NULL OR abort_reason IN ('dns', 'dnf', 'dsq')",
            name=op.f("ck_start_abort_reason"),
        ),
        sa.CheckConstraint(
            "(status = 'aborted') = (abort_reason IS NOT NULL)", name=op.f("ck_start_aborted")
        ),
        sa.CheckConstraint("attempt >= 1", name=op.f("ck_start_attempt")),
        sa.CheckConstraint("fee_cents >= 0", name=op.f("ck_start_fee_cents")),
        sa.CheckConstraint(
            "queue_position IS NULL OR queue_position >= 1", name=op.f("ck_start_queue_position")
        ),
        sa.CheckConstraint("lane IS NULL OR lane >= 1", name=op.f("ck_start_lane")),
        sa.CheckConstraint("heat_id IS NULL OR lane IS NOT NULL", name=op.f("ck_start_heat_lane")),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["entry.id"], name=op.f("fk_start_entry_id_entry"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"], ["competition.id"], name=op.f("fk_start_competition_id_competition")
        ),
        sa.ForeignKeyConstraint(
            ["heat_id"], ["heat.id"], name=op.f("fk_start_heat_id_heat"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_start")),
        sa.UniqueConstraint(
            "entry_id",
            "competition_id",
            "attempt",
            name="uq_start_attempt",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(op.f("ix_start_entry_id"), "start", ["entry_id"], unique=False)
    op.create_index(op.f("ix_start_competition_id"), "start", ["competition_id"], unique=False)
    op.create_index(op.f("ix_start_heat_id"), "start", ["heat_id"], unique=False)
    op.create_index(
        "uq_start_heat_lane",
        "start",
        ["heat_id", "lane"],
        unique=True,
        postgresql_where=sa.text("heat_id IS NOT NULL AND status <> 'aborted'"),
    )


def downgrade() -> None:
    op.drop_index("uq_start_heat_lane", table_name="start")
    op.drop_index(op.f("ix_start_heat_id"), table_name="start")
    op.drop_index(op.f("ix_start_competition_id"), table_name="start")
    op.drop_index(op.f("ix_start_entry_id"), table_name="start")
    op.drop_table("start")
    op.drop_index(op.f("ix_heat_range_id"), table_name="heat")
    op.drop_table("heat")
    op.drop_index(op.f("ix_entry_class_id"), table_name="entry")
    op.drop_index(op.f("ix_entry_person_id"), table_name="entry")
    op.drop_index(op.f("ix_entry_tournament_id"), table_name="entry")
    op.drop_table("entry")
