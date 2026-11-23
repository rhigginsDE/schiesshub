"""Führt die Zweige der vierten Welle zusammen (Sicherungsrechte, Übungsturnier).

Revision ID: 0017_merge
Revises: 0016_sicherung_rechte, 0016_turnier_uebung
"""

from collections.abc import Sequence

revision: str = "0017_merge"
down_revision: str | Sequence[str] | None = ("0016_sicherung_rechte", "0016_turnier_uebung")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
