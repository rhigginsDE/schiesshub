"""Führt die Zweige der ersten Kernmodule zusammen (Turnier, Teilnehmer, Auth, Sicherung).

Revision ID: 0006_merge
Revises: 0002_turnier, 0003_teilnehmer, 0004_auth, 0005_backup
"""

from collections.abc import Sequence

revision: str = "0006_merge"
down_revision: str | Sequence[str] | None = (
    "0002_turnier",
    "0003_teilnehmer",
    "0004_auth",
    "0005_backup",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
