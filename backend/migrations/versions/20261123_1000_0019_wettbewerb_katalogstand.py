"""Wettbewerb: Katalogfassung, aus der die Definition stammt (`competition.catalog_base`).

Damit lässt sich je Abruf und auf jedem Gerät sagen, ob sich der Katalog geändert hat, seit die
Definition aus ihm übernommen wurde („Katalog seit der Übernahme geändert“): Verglichen wird
`catalog_base` mit der aktuellen Katalog-Variante, nicht die (vielleicht bewusst abweichende)
Definition. Gesetzt beim Anlegen aus dem Katalog und beim Übernehmen (`reset-definition`); eine
Kopie („wie letztes Jahr“) übernimmt den Wert des Originals.

Vorhandene Wettbewerbe aus dem Katalog bekommen die Definition ihrer Revision 1 (die Übernahme
beim Anlegen). Bei schon kopierten Wettbewerben ist Revision 1 die Kopie samt Abweichungen des
Originals; dort kann der Vermerk deshalb auch bei unverändertem Katalog erscheinen, bis die
Definition einmal übernommen wird.

Revision ID: 0019_wettbewerb_katalogstand
Revises: 0018_katalog_dsb_klassen
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_wettbewerb_katalogstand"
down_revision: str | Sequence[str] | None = "0018_katalog_dsb_klassen"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("competition", sa.Column("catalog_base", postgresql.JSONB(), nullable=True))
    op.execute(
        """
        UPDATE competition AS c
        SET catalog_base = r.definition
        FROM competition_revision AS r
        WHERE r.competition_id = c.id
          AND r.revision = 1
          AND c.catalog_federation IS NOT NULL
          AND c.catalog_code IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("competition", "catalog_base")
