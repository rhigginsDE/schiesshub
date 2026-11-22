"""Gemeinsame Datenbank-Bausteine des Moduls `starts`: Nachschlagen, Sperren, Bahnbelegung.

`ConflictError` ist der gemeinsame Baustein aus `app.core.errors` (409, wahlweise mit Feld:
`ConflictError("Bahn 2 ist schon belegt.", field="lane")`).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.modules.starts.models import Entry, Start
from app.modules.turnier.models import Competition, Range, Tournament
from app.modules.turnier.service import NotFoundError

__all__ = [
    "ConflictError",
    "NotFoundError",
    "StartContext",
    "event_ids",
    "get_entry",
    "get_range",
    "get_start",
    "get_tournament",
    "occupied_on_range",
    "on_lane_entry_ids",
    "renumber_queue",
    "waiting_starts",
    "writable_tournament",
]


def event_ids(**ids: uuid.UUID | None) -> dict[str, str | None]:
    """Nutzlast eines Ereignisses: nur IDs, nie Namen."""
    return {key: str(value) if value is not None else None for key, value in ids.items()}


# --- Nachschlagen ------------------------------------------------------------


async def get_tournament(
    session: AsyncSession, tournament_id: uuid.UUID, *, lock: bool = False
) -> Tournament:
    query = select(Tournament).where(Tournament.id == tournament_id)
    if lock:
        query = query.with_for_update()
    tournament = await session.scalar(query)
    if tournament is None:
        raise NotFoundError("Das Turnier wurde nicht gefunden.")
    return tournament


async def writable_tournament(
    session: AsyncSession, tournament_id: uuid.UUID, *, lock: bool = False
) -> Tournament:
    tournament = await get_tournament(session, tournament_id, lock=lock)
    if tournament.status == "closed":
        raise ConflictError(
            "Das Turnier ist abgeschlossen. Anmeldungen und Starts lassen sich erst nach dem "
            "Wiederöffnen ändern."
        )
    return tournament


async def get_range(
    session: AsyncSession, tournament_id: uuid.UUID, range_id: uuid.UUID, *, lock: bool = False
) -> Range:
    """Stand des Turniers. Mit `lock` laufen alle Vorgänge an seinen Bahnen nacheinander."""
    query = select(Range).where(Range.id == range_id)
    if lock:
        query = query.with_for_update()
    item = await session.scalar(query)
    if item is None or item.tournament_id != tournament_id:
        raise NotFoundError("Der Stand wurde in diesem Turnier nicht gefunden.")
    return item


async def get_entry(session: AsyncSession, tournament_id: uuid.UUID, entry_id: uuid.UUID) -> Entry:
    entry = await session.get(Entry, entry_id)
    if entry is None or entry.tournament_id != tournament_id:
        raise NotFoundError("Die Anmeldung wurde in diesem Turnier nicht gefunden.")
    return entry


@dataclass(frozen=True, slots=True)
class StartContext:
    start: Start
    entry: Entry
    competition: Competition

    def audit_details(self, **extra: object) -> dict[str, object]:
        """Angaben für das System-Protokoll: Startnummer und Wettbewerb, nie der Name."""
        return {
            "tournament_id": str(self.entry.tournament_id),
            "entry_id": str(self.entry.id),
            "competition_id": str(self.competition.id),
            "competition_code": self.competition.catalog_code,
            "competition_name": self.competition.name,
            "start_number": self.entry.start_number,
            "attempt": self.start.attempt,
            **extra,
        }


async def get_start(
    session: AsyncSession, tournament_id: uuid.UUID, start_id: uuid.UUID
) -> StartContext:
    row = (
        await session.execute(
            select(Start, Entry, Competition)
            .join(Entry, Entry.id == Start.entry_id)
            .join(Competition, Competition.id == Start.competition_id)
            .where(Start.id == start_id, Entry.tournament_id == tournament_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Der Start wurde in diesem Turnier nicht gefunden.")
    return StartContext(*row)


# --- Reihenfolge und Bahnbelegung --------------------------------------------


async def waiting_starts(session: AsyncSession, range_id: uuid.UUID) -> list[Start]:
    """Wartende Starts der Reihenfolge eines Stands, in ihrer Reihenfolge.

    Starts ohne Platz (z. B. weil der Wettbewerb erst nachträglich einen Stand bekam) stehen
    hinten, nach Buchungszeit.
    """
    rows = await session.scalars(
        select(Start)
        .join(Competition, Competition.id == Start.competition_id)
        .where(
            Competition.range_id == range_id,
            Competition.planning == "queue",
            Start.status == "registered",
            Start.heat_id.is_(None),
        )
        .order_by(
            Start.queue_position.asc().nulls_last(),
            Start.created_at,
            Start.attempt,
            Start.id,
        )
    )
    return list(rows)


async def renumber_queue(session: AsyncSession, range_id: uuid.UUID) -> list[Start]:
    """Vergibt die Plätze der Reihenfolge lückenlos ab 1 und liefert die Wartenden."""
    waiting = await waiting_starts(session, range_id)
    for position, start in enumerate(waiting, start=1):
        if start.queue_position != position:
            start.queue_position = position
    return waiting


async def occupied_on_range(session: AsyncSession, range_id: uuid.UUID) -> dict[int, Start]:
    """Belegte Bahnen eines Stands: Bahn → Start auf ihr (aufgerufen oder erfasst, noch nicht
    freigegeben), über alle Wettbewerbe des Stands."""
    rows = await session.scalars(
        select(Start)
        .join(Competition, Competition.id == Start.competition_id)
        .where(Competition.range_id == range_id, Start.on_lane)
    )
    return {start.lane: start for start in rows if start.lane is not None}


async def on_lane_entry_ids(session: AsyncSession, tournament_id: uuid.UUID) -> set[uuid.UUID]:
    """Anmeldungen (also Personen), die im Turnier gerade auf einer Bahn stehen."""
    rows = await session.scalars(
        select(Start.entry_id)
        .join(Entry, Entry.id == Start.entry_id)
        .where(Entry.tournament_id == tournament_id, Start.on_lane)
    )
    return set(rows)
