"""Rechte: eigenes Recht `start.abort`, Startrolle „Anzeige“ nur noch mit `display.read`.

1. Einen Start abbrechen (nicht angetreten, aufgegeben, disqualifiziert) war bisher Teil von
   `start.call`. Jetzt gibt es dafür `start.abort`. Damit sich an bestehenden Installationen nichts
   ändert, bekommt jede Rolle, die `start.call` ausdrücklich führt, zusätzlich `start.abort`.
   Muster (`start.*`, `*`) decken das neue Recht ohnehin ab.
2. Die Startrolle „Anzeige“ brauchte nur den Feed der Anzeige, führte aber auch `start.read`,
   `result.read` und `tournament.read`. Sie wird auf `display.read` gekürzt – aber nur, wenn ihre
   Rechte noch genau der alten Vorlage entsprechen. Von Hand geänderte Rollen bleiben, wie sie sind.

Jede Änderung steht im Audit-Protokoll (`role.migrated`, vorher/nachher).

Revision ID: 0015_auth_rechte
Revises: 0014_politur
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_auth_rechte"
down_revision: str | Sequence[str] | None = "0014_politur"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CALL = "start.call"
ABORT = "start.abort"
DISPLAY_KEY = "Anzeige"
DISPLAY_OLD = ["display.read", "start.read", "result.read", "tournament.read"]
DISPLAY_NEW = ["display.read"]


def _with_abort(entries: list[str]) -> list[str]:
    if CALL not in entries or ABORT in entries:
        return entries
    position = entries.index(CALL) + 1
    return [*entries[:position], ABORT, *entries[position:]]


def _upgraded(entries: list[str], starter_key: str | None) -> list[str]:
    if starter_key == DISPLAY_KEY and set(entries) == set(DISPLAY_OLD):
        return list(DISPLAY_NEW)
    return _with_abort(entries)


def _downgraded(entries: list[str], starter_key: str | None) -> list[str]:
    if starter_key == DISPLAY_KEY and entries == DISPLAY_NEW:
        return list(DISPLAY_OLD)
    return [entry for entry in entries if entry != ABORT]


def migrate_roles(connection: sa.Connection, *, downgrade: bool = False) -> int:
    """Passt die Rechte aller Rollen außer der Systemrolle an; liefert die Zahl der Änderungen."""
    rows = connection.execute(
        sa.text(
            "SELECT id, name, permissions, starter_key FROM role WHERE NOT is_system ORDER BY name"
        )
    ).all()
    changed = 0
    for row in rows:
        before = list(row.permissions or [])
        change = _downgraded if downgrade else _upgraded
        after = change(before, row.starter_key)
        if after == before:
            continue
        connection.execute(
            sa.text("UPDATE role SET permissions = CAST(:permissions AS jsonb) WHERE id = :id"),
            {"permissions": json.dumps(after), "id": row.id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO audit_log (id, action, entity, entity_id, details) "
                "VALUES (:id, 'role.migrated', 'role', :entity_id, CAST(:details AS jsonb))"
            ),
            {
                "id": uuid.uuid4(),
                "entity_id": str(row.id),
                "details": json.dumps(
                    {
                        "name": row.name,
                        "before": before,
                        "after": after,
                        "via": f"Datenbank-Aktualisierung {revision}",
                    }
                ),
            },
        )
        changed += 1
    return changed


def upgrade() -> None:
    migrate_roles(op.get_bind())


def downgrade() -> None:
    migrate_roles(op.get_bind(), downgrade=True)
