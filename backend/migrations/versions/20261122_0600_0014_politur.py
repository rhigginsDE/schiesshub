"""Bahnbelegung als eigenes Kennzeichen am Start (`start.on_lane`).

Bisher galt eine Bahn nur als belegt, solange ein Start `called` war; mit der ersten Eingabe
(`captured`) wurde sie frei, obwohl der Schütze noch schießt. Jetzt steht die Belegung in
`on_lane`: gesetzt beim Aufruf, gelöscht bei `final`, `aborted`, beim Zurückstellen oder über
„Bahn freigeben“. Bestehende Starts: belegt ist, was gerade `called` ist (wie bisher).

Revision ID: 0014_politur
Revises: 0013_merge
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_politur"
down_revision: str | Sequence[str] | None = "0013_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "start",
        sa.Column("on_lane", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute("UPDATE start SET on_lane = true WHERE status = 'called' AND lane IS NOT NULL")
    op.create_check_constraint(
        op.f("ck_start_on_lane"),
        "start",
        "NOT on_lane OR (lane IS NOT NULL AND status IN ('called', 'captured'))",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_start_on_lane"), "start", type_="check")
    op.drop_column("start", "on_lane")
