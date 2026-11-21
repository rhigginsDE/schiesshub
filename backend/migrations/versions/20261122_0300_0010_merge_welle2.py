"""Führt die Zweige der zweiten Welle zusammen (Turnier-Versionen, Starts, Ergebnisse).

Revision ID: 0010_merge
Revises: 0008_turnier_versionen, 0009_ergebnisse
"""

from collections.abc import Sequence

revision: str = "0010_merge"
down_revision: str | Sequence[str] | None = ("0008_turnier_versionen", "0009_ergebnisse")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
