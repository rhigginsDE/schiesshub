"""Katalog: Verband, Gruppe, Disziplin, Klasse und Importstatus.

Revision ID: 0001
Revises: -
Create Date: 2026-11-21 21:46:11.159256+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_federation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("short_name", sa.String(length=40), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("rulebook_name", sa.Text(), nullable=False),
        sa.Column("rulebook_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("classes_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_federation")),
        sa.UniqueConstraint("key", name=op.f("uq_catalog_federation_key")),
    )
    op.create_table(
        "catalog_import_state",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_import_state")),
    )
    op.create_table(
        "catalog_class",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("federation_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.String(length=40), nullable=False),
        sa.Column("gender", sa.String(length=20), nullable=False),
        sa.Column("age_hint", sa.Text(), nullable=True),
        sa.Column("min_starters_dm", sa.Integer(), nullable=True),
        sa.Column("merge_into", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("merge_by_age", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["federation_id"],
            ["catalog_federation.id"],
            name=op.f("fk_catalog_class_federation_id_catalog_federation"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_class")),
        sa.UniqueConstraint("federation_id", "key", name=op.f("uq_catalog_class_federation_id")),
    )
    op.create_table(
        "catalog_group",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("federation_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("weapon_type", sa.String(length=20), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("scoring", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("procedures", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["federation_id"],
            ["catalog_federation.id"],
            name=op.f("fk_catalog_group_federation_id_catalog_federation"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_group")),
        sa.UniqueConstraint("federation_id", "key", name=op.f("uq_catalog_group_federation_id")),
    )
    op.create_table(
        "catalog_discipline",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("federation_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("weapon", sa.Text(), nullable=False),
        sa.Column("ammunition", sa.Text(), nullable=False),
        sa.Column("sights", sa.Text(), nullable=False),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("procedure_key", sa.String(length=80), nullable=False),
        sa.Column("optional", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("to_check", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("former_code", sa.String(length=40), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["federation_id"],
            ["catalog_federation.id"],
            name=op.f("fk_catalog_discipline_federation_id_catalog_federation"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["catalog_group.id"],
            name=op.f("fk_catalog_discipline_group_id_catalog_group"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_discipline")),
        sa.UniqueConstraint(
            "federation_id", "code", name=op.f("uq_catalog_discipline_federation_id")
        ),
    )
    op.create_index(
        op.f("ix_catalog_discipline_group_id"), "catalog_discipline", ["group_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_catalog_discipline_group_id"), table_name="catalog_discipline")
    op.drop_table("catalog_discipline")
    op.drop_table("catalog_group")
    op.drop_table("catalog_class")
    op.drop_table("catalog_import_state")
    op.drop_table("catalog_federation")
