"""Turnier: Übungsturnier (`is_practice`) und seine Übungsdaten (`practice_data`).

1. `tournament.is_practice` kennzeichnet das Übungsturnier mit Beispieldaten. Es gibt höchstens
   eines (eindeutiger Teilindex). Die Kennzeichnung steht beim Anlegen fest und lässt sich danach
   nicht mehr ändern (Trigger): Ein echtes Turnier kann nicht nachträglich zur Übung werden.
2. `tournament.practice_data` nennt die Personen und Vereine, die das Übungsturnier angelegt hat,
   damit „Übung entfernen“ genau diese wieder löscht.
3. `result_event` bleibt unveränderlich. Einzige Ausnahme: DELETE von Ereignissen, deren Start zu
   einem Übungsturnier gehört – nur so lässt sich die Übung samt Ergebnissen rückstandsfrei
   entfernen. UPDATE bleibt immer verboten, DELETE in echten Turnieren auch.

Revision ID: 0016_turnier_uebung
Revises: 0015_auth_rechte
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_turnier_uebung"
down_revision: str | Sequence[str] | None = "0015_auth_rechte"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Wie in 0009_ergebnisse, plus die Ausnahme für das Übungsturnier.
IMMUTABLE_WITH_PRACTICE = """
CREATE OR REPLACE FUNCTION result_event_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND EXISTS (
        SELECT 1
        FROM start
        JOIN entry ON entry.id = start.entry_id
        JOIN tournament ON tournament.id = entry.tournament_id
        WHERE start.id = OLD.start_id AND tournament.is_practice
    ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'result_event ist unveränderlich: % ist nicht erlaubt', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$
"""
IMMUTABLE_ORIGINAL = """
CREATE OR REPLACE FUNCTION result_event_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'result_event ist unveränderlich: % ist nicht erlaubt', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$
"""
PRACTICE_FIXED_FUNCTION = """
CREATE FUNCTION tournament_practice_fixed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'tournament.is_practice lässt sich nach dem Anlegen nicht ändern'
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$
"""
PRACTICE_FIXED_TRIGGER = """
CREATE TRIGGER tournament_practice_fixed
BEFORE UPDATE ON tournament
FOR EACH ROW
WHEN (OLD.is_practice IS DISTINCT FROM NEW.is_practice)
EXECUTE FUNCTION tournament_practice_fixed()
"""


def upgrade() -> None:
    op.add_column(
        "tournament",
        sa.Column("is_practice", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "tournament",
        sa.Column("practice_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "uq_tournament_practice",
        "tournament",
        ["is_practice"],
        unique=True,
        postgresql_where=sa.text("is_practice"),
    )
    op.execute(PRACTICE_FIXED_FUNCTION)
    op.execute(PRACTICE_FIXED_TRIGGER)
    op.execute(IMMUTABLE_WITH_PRACTICE)


def downgrade() -> None:
    op.execute(IMMUTABLE_ORIGINAL)
    op.execute("DROP TRIGGER tournament_practice_fixed ON tournament")
    op.execute("DROP FUNCTION tournament_practice_fixed()")
    op.drop_index("uq_tournament_practice", table_name="tournament")
    op.drop_column("tournament", "practice_data")
    op.drop_column("tournament", "is_practice")
