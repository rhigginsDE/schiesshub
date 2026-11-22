"""Tabellen des Moduls `starts`: Anmeldung, Start, Durchgang (siehe docs/DATENMODELL.md).

Die Bahnbelegung gehört zum Stand: Eine Bahn ist belegt, solange ein Start mit Status `called`
auf ihr steht (Stand über `competition.range_id`). Mit `captured`, `final` oder `aborted` ist sie
wieder frei; `lane` bleibt als Angabe erhalten, auf welcher Bahn geschossen wurde.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey


class Entry(UUIDPrimaryKey, Timestamps, Base):
    """Anmeldung einer Person in einem Turnier, trägt die Startnummer."""

    __tablename__ = "entry"
    __table_args__ = (
        UniqueConstraint("tournament_id", "start_number", name="uq_entry_start_number"),
        UniqueConstraint("tournament_id", "person_id", name="uq_entry_person"),
        CheckConstraint("start_number >= 1", name="start_number"),
    )

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tournament.id", ondelete="CASCADE"), index=True
    )
    # Ohne ON DELETE: Personen und Klassen mit Anmeldungen lassen sich nicht löschen.
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tournament_class.id"), index=True)
    start_number: Mapped[int] = mapped_column(Integer)


class Heat(UUIDPrimaryKey, Timestamps, Base):
    """Durchgang: Zeitfenster auf einem Stand (nur bei Zeitplan). Kapazität = Bahnen des Stands."""

    __tablename__ = "heat"
    __table_args__ = (
        UniqueConstraint("range_id", "number", name="uq_heat_number"),
        CheckConstraint("number >= 1", name="number"),
        CheckConstraint("ends_at > starts_at", name="times"),
    )

    range_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("range.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Start(UUIDPrimaryKey, Timestamps, Base):
    """Ein gebuchter Start in einem Wettbewerb. Betrag und Bahn hängen am Start."""

    __tablename__ = "start"
    __table_args__ = (
        # Aufgeschoben, damit das Nachrücken nach einem Storno in einer Transaktion gelingt.
        UniqueConstraint(
            "entry_id",
            "competition_id",
            "attempt",
            name="uq_start_attempt",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "status IN ('registered', 'called', 'captured', 'final', 'aborted')", name="status"
        ),
        CheckConstraint(
            "abort_reason IS NULL OR abort_reason IN ('dns', 'dnf', 'dsq')", name="abort_reason"
        ),
        CheckConstraint("(status = 'aborted') = (abort_reason IS NOT NULL)", name="aborted"),
        CheckConstraint("attempt >= 1", name="attempt"),
        CheckConstraint("fee_cents >= 0", name="fee_cents"),
        CheckConstraint("queue_position IS NULL OR queue_position >= 1", name="queue_position"),
        CheckConstraint("lane IS NULL OR lane >= 1", name="lane"),
        CheckConstraint("heat_id IS NULL OR lane IS NOT NULL", name="heat_lane"),
        # Ein Platz (Bahn) je Durchgang; abgebrochene Starts geben ihn frei.
        Index(
            "uq_start_heat_lane",
            "heat_id",
            "lane",
            unique=True,
            postgresql_where=text("heat_id IS NOT NULL AND status <> 'aborted'"),
        ),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entry.id", ondelete="CASCADE"), index=True
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competition.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    # Beim Buchen festgeschrieben; spätere Preisänderungen am Wettbewerb ändern ihn nicht.
    fee_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    abort_reason: Mapped[str | None] = mapped_column(String(10))
    # Platz in der Reihenfolge des Stands, nur solange der Start dort wartet (lückenlos ab 1).
    queue_position: Mapped[int | None] = mapped_column(Integer)
    heat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("heat.id", ondelete="SET NULL"), index=True
    )
    lane: Mapped[int | None] = mapped_column(Integer)
