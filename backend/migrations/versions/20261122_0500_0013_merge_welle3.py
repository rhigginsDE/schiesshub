"""Führt die Zweige der dritten Welle zusammen (Anzeige, Nacharbeiten).

Revision ID: 0013_merge
Revises: 0011_anzeige, 0012_nacharbeiten
"""

from collections.abc import Sequence

revision: str = "0013_merge"
down_revision: str | Sequence[str] | None = ("0011_anzeige", "0012_nacharbeiten")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
