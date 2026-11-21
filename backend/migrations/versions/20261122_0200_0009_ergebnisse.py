"""Ergebnisse: Ereignisprotokoll (result_event, nur Einfügen) und aktueller Stand (result_current).

Ein Trigger weist UPDATE und DELETE auf `result_event` ab; Ergebnisse werden nie überschrieben.

Revision ID: 0009_ergebnisse
Revises: 0007_starts
Create Date: 2026-11-22 02:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_ergebnisse"
down_revision: str | Sequence[str] | None = "0007_starts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_FUNCTION = """
CREATE FUNCTION result_event_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'result_event ist unveränderlich: % ist nicht erlaubt', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$
"""
IMMUTABLE_TRIGGER = """
CREATE TRIGGER result_event_immutable
BEFORE UPDATE OR DELETE ON result_event
FOR EACH ROW EXECUTE FUNCTION result_event_immutable()
"""


def upgrade() -> None:
    op.create_table(
        "result_event",
        sa.Column("start_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("seq >= 1", name=op.f("ck_result_event_seq")),
        sa.CheckConstraint(
            "type IN ('raw_set', 'finalized', 'corrected', 'reopened', 'aborted')",
            name=op.f("ck_result_event_type"),
        ),
        sa.CheckConstraint(
            "type NOT IN ('corrected', 'reopened') OR (reason IS NOT NULL AND btrim(reason) <> '')",
            name=op.f("ck_result_event_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["start_id"], ["start.id"], name=op.f("fk_result_event_start_id_start")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_result_event")),
        sa.UniqueConstraint("start_id", "seq", name=op.f("uq_result_event_start_id")),
    )
    op.create_index(op.f("ix_result_event_start_id"), "result_event", ["start_id"], unique=False)
    op.create_index(
        "uq_result_event_idempotency",
        "result_event",
        ["start_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.execute(IMMUTABLE_FUNCTION)
    op.execute(IMMUTABLE_TRIGGER)

    op.create_table(
        "result_current",
        sa.Column("start_id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("score", sa.Numeric(), nullable=True),
        sa.Column("rank_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provisional_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seq", sa.Integer(), nullable=False),
        sa.Column("definition_revision", sa.Integer(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("last_seq >= 1", name=op.f("ck_result_current_last_seq")),
        sa.ForeignKeyConstraint(
            ["start_id"], ["start.id"], name=op.f("fk_result_current_start_id_start")
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["competition.id"],
            name=op.f("fk_result_current_competition_id_competition"),
        ),
        sa.PrimaryKeyConstraint("start_id", name=op.f("pk_result_current")),
    )
    op.create_index(
        op.f("ix_result_current_competition_id"),
        "result_current",
        ["competition_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_result_current_competition_id"), table_name="result_current")
    op.drop_table("result_current")
    op.execute("DROP TRIGGER result_event_immutable ON result_event")
    op.execute("DROP FUNCTION result_event_immutable()")
    op.drop_index("uq_result_event_idempotency", table_name="result_event")
    op.drop_index(op.f("ix_result_event_start_id"), table_name="result_event")
    op.drop_table("result_event")
