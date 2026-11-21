"""Tabellen des Turniers: Turnier, Stand, Klasse, Wettbewerb (siehe docs/DATENMODELL.md)."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey


class Tournament(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "tournament"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'closed')", name="status"),
        CheckConstraint("template IN ('open', 'club_championship', 'custom')", name="template"),
        CheckConstraint("date_to >= date_from", name="dates"),
    )

    name: Mapped[str] = mapped_column(String(200))
    organizer: Mapped[str | None] = mapped_column(String(200))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    template: Mapped[str] = mapped_column(String(30))
    # Vollständig nach schemas.TournamentSettings, inklusive der Standardwerte.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Range(UUIDPrimaryKey, Timestamps, Base):
    """Schießstand mit nummerierten Bahnen."""

    __tablename__ = "range"
    __table_args__ = (CheckConstraint("lane_count >= 1", name="lane_count"),)

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tournament.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    lane_count: Mapped[int] = mapped_column(Integer)
    sort: Mapped[int] = mapped_column(Integer)


class TournamentClass(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "tournament_class"
    __table_args__ = (UniqueConstraint("tournament_id", "code"),)

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tournament.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    short: Mapped[str] = mapped_column(String(40))
    sort: Mapped[int] = mapped_column(Integer)
    # Zusammenlegung: Kommt die Klasse nicht zustande, wird sie in diese Klasse gewertet.
    merge_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tournament_class.id", ondelete="SET NULL")
    )


class Competition(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "competition"
    __table_args__ = (
        CheckConstraint("capture_mode IN ('shot', 'series')", name="capture_mode"),
        CheckConstraint("multi_start_rule IN ('best', 'first', 'all')", name="multi_start_rule"),
        CheckConstraint("planning IN ('queue', 'schedule')", name="planning"),
        CheckConstraint("max_starts >= 1", name="max_starts"),
        CheckConstraint("fee_first_cents >= 0 AND fee_repeat_cents >= 0", name="fees"),
        CheckConstraint("heat_minutes IS NULL OR heat_minutes >= 1", name="heat_minutes"),
        CheckConstraint("changeover_minutes >= 0", name="changeover_minutes"),
    )

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tournament.id", ondelete="CASCADE"), index=True
    )
    range_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("range.id", ondelete="SET NULL"), index=True
    )
    sort: Mapped[int] = mapped_column(Integer)
    # Herkunft aus dem Katalog (Verbandsschlüssel und Kennziffer), leer bei eigener Disziplin.
    catalog_federation: Mapped[str | None] = mapped_column(String(80))
    catalog_code: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    # Kopie von Ablauf-Variante und Wertung, nach schemas.CompetitionDefinition.
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    capture_mode: Mapped[str] = mapped_column(String(20))
    multi_start: Mapped[bool] = mapped_column(Boolean)
    max_starts: Mapped[int] = mapped_column(Integer)
    multi_start_rule: Mapped[str] = mapped_column(String(20))
    fee_first_cents: Mapped[int] = mapped_column(Integer)
    fee_repeat_cents: Mapped[int] = mapped_column(Integer)
    # Zugelassene Klassen (tournament_class.id). Leer: alle Klassen des Turniers.
    class_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid))
    combined_ranking: Mapped[bool] = mapped_column(Boolean)
    planning: Mapped[str] = mapped_column(String(20))
    # Dauer eines Durchgangs einschließlich Wechselzeit.
    heat_minutes: Mapped[int | None] = mapped_column(Integer)
    changeover_minutes: Mapped[int] = mapped_column(Integer)
