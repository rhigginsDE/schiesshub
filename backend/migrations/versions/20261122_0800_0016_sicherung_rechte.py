"""Rechte der Sicherung: eigenes Recht `backup.run`, neues Recht `backup.restore`.

1. „Jetzt sichern“ war bisher Teil von `backup.manage`. Jetzt gibt es dafür `backup.run`. Damit
   sich an bestehenden Installationen nichts ändert, bekommt jede Rolle, die `backup.manage`
   ausdrücklich führt, zusätzlich `backup.run`.
2. Die Startrolle „Turnierleitung“ darf die Sicherung auslösen (Entscheidung vom 22.11.2026). Sie
   bekommt `backup.run` – aber nur, wenn ihre Rechte noch genau der alten Vorlage entsprechen. Von
   Hand geänderte Rollen bleiben, wie sie sind.
3. `backup.restore` (Sicherung wiederherstellen) soll nur der Administrator haben. Eine Rolle mit
   dem Muster `backup.*` bekäme es sonst still dazu. Das Muster wird deshalb durch die bisher
   gemeinten Rechte ersetzt (`backup.read`, `backup.manage`, `backup.run`); das Verhalten bleibt
   gleich. Wer eine Rolle wirklich wiederherstellen lassen will, trägt `backup.restore` selbst ein.

Die Systemrolle hat immer alle Rechte und bleibt unberührt. Jede Änderung steht im
Audit-Protokoll (`role.migrated`, vorher/nachher).

Revision ID: 0016_sicherung_rechte
Revises: 0015_auth_rechte
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_sicherung_rechte"
down_revision: str | Sequence[str] | None = "0015_auth_rechte"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MANAGE = "backup.manage"
RUN = "backup.run"
AREA = "backup.*"
AREA_EXPANDED = ["backup.read", "backup.manage", "backup.run"]
LEAD_KEY = "Turnierleitung"
LEAD_OLD = [
    "tournament.*",
    "entry.*",
    "start.*",
    "result.*",
    "person.*",
    "club.edit",
    "export.*",
    "display.*",
    "backup.read",
]
LEAD_NEW = [*LEAD_OLD, RUN]


def _insert_after(entries: list[str], anchor: str, new: str) -> list[str]:
    position = entries.index(anchor) + 1
    return [*entries[:position], new, *entries[position:]]


def _upgraded(entries: list[str], starter_key: str | None) -> list[str]:
    if starter_key == LEAD_KEY and set(entries) == set(LEAD_OLD):
        return list(LEAD_NEW)
    if AREA in entries:
        position = entries.index(AREA)
        expanded = [entry for entry in AREA_EXPANDED if entry not in entries]
        entries = [*entries[:position], *expanded, *entries[position + 1 :]]
    if MANAGE in entries and RUN not in entries:
        entries = _insert_after(entries, MANAGE, RUN)
    return entries


def _downgraded(entries: list[str], starter_key: str | None) -> list[str]:
    if starter_key == LEAD_KEY and entries == LEAD_NEW:
        return list(LEAD_OLD)
    # `backup.run` gibt es vor dieser Fassung nicht; `backup.manage` deckt es dort ab.
    return [entry for entry in entries if entry != RUN]


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
