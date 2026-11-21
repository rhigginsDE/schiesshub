"""Tabellen des Moduls `ergebnisse`: Ereignisprotokoll und aktueller Stand (docs/DATENMODELL.md).

`result_event` ist das unveränderliche Protokoll: nur Einfügen. Ein Trigger in der Datenbank
weist UPDATE und DELETE ab (Migration `0009_ergebnisse`), damit auch ein Fehler im Code oder ein
Zugriff von Hand nichts überschreiben kann.

`result_current` ist abgeleitet: Rohwerte und Wertung nach dem letzten Ereignis, berechnet mit der
Definition des Wettbewerbs in der Revision `definition_revision`. Die Zeile lässt sich jederzeit
aus den Ereignissen neu aufbauen (`recompute.py`).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey


class ResultEvent(UUIDPrimaryKey, Base):
    """Ein Ereignis zu einem Start: Eingabe, Abschluss, Korrektur, Wiederöffnen, Abbruch."""

    __tablename__ = "result_event"
    __table_args__ = (
        UniqueConstraint("start_id", "seq"),
        CheckConstraint("seq >= 1", name="seq"),
        CheckConstraint(
            "type IN ('raw_set', 'finalized', 'corrected', 'reopened', 'aborted')", name="type"
        ),
        CheckConstraint(
            "type NOT IN ('corrected', 'reopened') OR (reason IS NOT NULL AND btrim(reason) <> '')",
            name="reason",
        ),
        # Ein Schlüssel gilt je Start genau einmal (Wiederholung nach Verbindungsabbruch).
        Index(
            "uq_result_event_idempotency",
            "start_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    # Ohne ON DELETE: Ein Start mit Ergebnis-Ereignissen lässt sich nicht löschen.
    start_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("start.id"), index=True)
    # Fortlaufend je Start ab 1; vergibt nur der Server.
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))
    # raw_set/corrected: {"raw": …}; finalized/corrected: {"provisional_until": …};
    # aborted: {"abort_reason": …}.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    # Wer und womit (ohne Fremdschlüssel, damit das Protokoll bleibt). Leer ohne Anmeldung.
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    # SHA-256 über Vorgang und Inhalt der Anfrage, um Wiederholungen zu erkennen.
    request_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ResultCurrent(Timestamps, Base):
    """Aktueller Stand eines Starts, abgeleitet aus seinen Ereignissen."""

    __tablename__ = "result_current"
    __table_args__ = (CheckConstraint("last_seq >= 1", name="last_seq"),)

    start_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("start.id"), primary_key=True)
    competition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competition.id"), index=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Wertung mit Rechenweg (`app.scoring.ComputedResult`); leer, wenn sich die Rohwerte mit der
    # aktuellen Definition nicht werten lassen (dann `needs_review`).
    computed: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    score: Mapped[Decimal | None] = mapped_column(Numeric)
    rank_keys: Mapped[list[int | None] | None] = mapped_column(JSONB)
    is_final: Mapped[bool] = mapped_column(Boolean)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Bis dahin gilt das Ergebnis als vorläufig (Einspruchsfrist); leer ohne Frist.
    provisional_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seq: Mapped[int] = mapped_column(Integer)
    # Revision der Definition, mit der `computed` berechnet wurde.
    definition_revision: Mapped[int] = mapped_column(Integer)
    # Abgeschlossen, aber nach einer Änderung der Wertung unvollständig oder nicht wertbar.
    needs_review: Mapped[bool] = mapped_column(Boolean, server_default="false")
    review_reason: Mapped[str | None] = mapped_column(Text)
