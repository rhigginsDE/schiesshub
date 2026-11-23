"""Katalog: Klassennummer, Klassensatz und Höhermeldung je Klasse, Startrecht je Verband.

Für den DSB-Katalog: Klassen haben dort offizielle Nummern ("10" = Herren I), die nur innerhalb
eines Klassensatzes (Sportschießen, Auflage, Bogen …) eindeutig sind. `start_rights` ist der
Inhalt von `<verband>/startrecht.yaml`.

Revision ID: 0018_katalog_dsb_klassen
Revises: 0017_merge
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_katalog_dsb_klassen"
down_revision: str | Sequence[str] | None = "0017_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("catalog_class", sa.Column("number", sa.String(40), nullable=True))
    op.add_column("catalog_class", sa.Column("class_set", sa.String(80), nullable=True))
    op.add_column(
        "catalog_class",
        sa.Column(
            "promote_to",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "catalog_federation", sa.Column("start_rights", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("catalog_federation", "start_rights")
    op.drop_column("catalog_class", "promote_to")
    op.drop_column("catalog_class", "class_set")
    op.drop_column("catalog_class", "number")
