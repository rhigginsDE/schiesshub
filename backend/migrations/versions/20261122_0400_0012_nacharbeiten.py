"""Rollen: Herkunft aus den Startrollen und „von Hand geändert“; Start: Zeitpunkt des Aufrufs.

`start.called_at` hält fest, wann ein Start auf die Bahn gerufen wurde (für „seit hh:mm“).
Bestehende aufgerufene Starts bekommen ihren letzten Änderungszeitpunkt als Näherung.

`starter_key` nennt die Startrolle, aus der eine Rolle entstand; `customized` sagt, ob ihre
Rechte seitdem von Hand geändert wurden. Damit gleicht der Server beim Start unveränderte
Startrollen an die aktuelle Zuordnung an (siehe `app.modules.auth.service.reconcile_roles`).

Bestehende Rollen: Startrolle ist, wer heute so heißt wie eine Startrolle. Von Hand geändert
ist eine Rolle, zu der das Audit-Protokoll eine Änderung der Rechte (`role.updated` mit
`permissions`) kennt.

Revision ID: 0012_nacharbeiten
Revises: 0010_merge
Create Date: 2026-11-22 04:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_nacharbeiten"
down_revision: str | Sequence[str] | None = "0010_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Stand der Startrollen beim Schreiben dieser Migration (bewusst nicht aus dem Code importiert).
STARTER_NAMES = ("Administrator", "Turnierleitung", "Kasse", "Auswertung", "Anzeige")


def upgrade() -> None:
    op.add_column("start", sa.Column("called_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE start SET called_at = updated_at WHERE status = 'called'")
    op.add_column("role", sa.Column("starter_key", sa.String(length=80), nullable=True))
    op.add_column(
        "role",
        sa.Column("customized", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        sa.text("UPDATE role SET starter_key = name WHERE name = ANY(:names)").bindparams(
            sa.bindparam("names", value=list(STARTER_NAMES), type_=sa.ARRAY(sa.String()))
        )
    )
    op.execute(
        """
        UPDATE role SET customized = true
        WHERE EXISTS (
            SELECT 1 FROM audit_log
            WHERE audit_log.action = 'role.updated'
              AND audit_log.entity_id = role.id::text
              AND audit_log.details -> 'permissions' IS NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.drop_column("start", "called_at")
    op.drop_column("role", "customized")
    op.drop_column("role", "starter_key")
