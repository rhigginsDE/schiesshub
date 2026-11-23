"""Tabellen des Turniers: Turnier, Schießstand, Klasse, Wettbewerb und dessen Revisionen.

Siehe docs/DATENMODELL.md.
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    text,
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
        # Höchstens ein Übungsturnier (Migration 0016_turnier_uebung).
        Index(
            "uq_tournament_practice",
            "is_practice",
            unique=True,
            postgresql_where=text("is_practice"),
        ),
    )

    name: Mapped[str] = mapped_column(String(200))
    organizer: Mapped[str | None] = mapped_column(String(200))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    template: Mapped[str] = mapped_column(String(30))
    # Vollständig nach schemas.TournamentSettings, inklusive der Standardwerte.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Ausschreibung nach schemas.Announcement. Leer bei Turnieren von vor dieser Spalte; dann
    # gilt die Standardgliederung der Vorlage.
    announcement: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Übungsturnier mit Beispieldaten (`POST /tournaments/practice`). Steht beim Anlegen fest; ein
    # Trigger verhindert die spätere Änderung.
    is_practice: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    # Nur beim Übungsturnier: die Personen und Vereine, die es angelegt hat
    # (`{"person_ids": […], "club_ids": […]}`), damit „Übung entfernen“ genau sie löscht.
    practice_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Range(UUIDPrimaryKey, Timestamps, Base):
    """Schießstand mit nummerierten Schützenständen (`lane_count`)."""

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
    # Katalogfassung, aus der die Definition stammt (wie `definition`, ohne eigene Änderungen):
    # gesetzt beim Anlegen aus dem Katalog und beim Übernehmen (`reset-definition`), bei einer
    # Kopie vom Original. Daran misst sich „Katalog seit der Übernahme geändert“. Leer bei eigenen
    # Wettbewerben (Migration 0019_wettbewerb_katalogstand).
    catalog_base: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
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
    # Aktuelle Revision (competition_revision.revision) der wertungsrelevanten Felder.
    definition_revision: Mapped[int] = mapped_column(Integer, server_default="1")


class CompetitionRevision(UUIDPrimaryKey, Timestamps, Base):
    """Stand der wertungsrelevanten Felder eines Wettbewerbs; nur Einfügen, nie ändern.

    Jede Änderung an Definition, Erfassungsart oder Mehrfachstart-Regeln legt eine neue Revision
    an. Ergebnisse lassen sich damit nachvollziehen und nach einer Änderung neu berechnen.
    """

    __tablename__ = "competition_revision"
    __table_args__ = (
        UniqueConstraint("competition_id", "revision"),
        CheckConstraint("revision >= 1", name="revision"),
    )

    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competition.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    capture_mode: Mapped[str] = mapped_column(String(20))
    multi_start: Mapped[bool] = mapped_column(Boolean)
    max_starts: Mapped[int] = mapped_column(Integer)
    multi_start_rule: Mapped[str] = mapped_column(String(20))
    combined_ranking: Mapped[bool] = mapped_column(Boolean)
    # Wer geändert hat (ohne Fremdschlüssel, damit die Revision bleibt). Leer ohne Anmeldung.
    changed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Pflicht, sobald das Turnier läuft (`active`).
    reason: Mapped[str | None] = mapped_column(Text)
