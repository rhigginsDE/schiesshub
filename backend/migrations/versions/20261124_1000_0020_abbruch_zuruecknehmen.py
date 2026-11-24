"""Ergebnisprotokoll: neue Ereignisart `abort_undone` (Abbruch zurücknehmen, mit Grund).

Ein Abbruch (dns, dnf, dsq) lässt sich mit Grund zurücknehmen; das steht als eigenes Ereignis im
Protokoll (nichts wird überschrieben). Die Prüfungen der Tabelle `result_event` nehmen die Art
auf; wie bei `corrected` und `reopened` ist ein Grund Pflicht.

Zurück (downgrade) geht nur, solange es kein Ereignis `abort_undone` gibt.

Revision ID: 0020_abbruch_zuruecknehmen
Revises: 0019_wettbewerb_katalogstand
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_abbruch_zuruecknehmen"
down_revision: str | Sequence[str] | None = "0019_wettbewerb_katalogstand"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPES_OLD = "type IN ('raw_set', 'finalized', 'corrected', 'reopened', 'aborted')"
TYPES_NEW = "type IN ('raw_set', 'finalized', 'corrected', 'reopened', 'aborted', 'abort_undone')"
REASON_OLD = "type NOT IN ('corrected', 'reopened') OR (reason IS NOT NULL AND btrim(reason) <> '')"
REASON_NEW = (
    "type NOT IN ('corrected', 'reopened', 'abort_undone') "
    "OR (reason IS NOT NULL AND btrim(reason) <> '')"
)


def _replace(types: str, reason: str) -> None:
    op.drop_constraint(op.f("ck_result_event_type"), "result_event", type_="check")
    op.drop_constraint(op.f("ck_result_event_reason"), "result_event", type_="check")
    op.create_check_constraint(op.f("ck_result_event_type"), "result_event", types)
    op.create_check_constraint(op.f("ck_result_event_reason"), "result_event", reason)


def upgrade() -> None:
    _replace(TYPES_NEW, REASON_NEW)


def downgrade() -> None:
    _replace(TYPES_OLD, REASON_OLD)
