"""Zeitplan: Durchgänge je Schießstand, Plätze (Durchgang + Schützenstand) und Aufruf eines
Durchgangs.

Ein Durchgang gehört zum Schießstand, nicht zum Wettbewerb; Wettbewerbe auf demselben Schießstand
teilen sich seine Schützenstände. Die Kapazität eines Durchgangs ist die Zahl der Schützenstände.
Durchgänge eines Schießstands überschneiden sich nicht, und eine Person steht nie in zwei
Durchgängen zur selben Zeit.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import CodedError, InputError
from app.core.events import EventHub
from app.core.localtime import zone_of
from app.core.security import Actor
from app.modules.auth.audit import record_audit
from app.modules.starts.common import (
    ConflictError,
    NotFoundError,
    event_ids,
    get_entry,
    get_range,
    get_start,
    get_tournament,
    occupied_on_range,
    on_lane_entry_ids,
    writable_tournament,
)
from app.modules.starts.lifecycle import StatusChange, publish_status, transition
from app.modules.starts.models import Entry, Heat, Start
from app.modules.starts.rules import (
    first_free_lane,
    heat_is_reserving,
    heat_reserve_minutes,
    heat_series,
    lane_list,
    overlaps,
)
from app.modules.starts.schemas import (
    HeatCreate,
    HeatOut,
    HeatReservationOut,
    HeatSeries,
    HeatUpdate,
)
from app.modules.turnier.models import Competition, Range, Tournament

EVENT_HEAT_CREATED = "heat.created"
EVENT_HEAT_UPDATED = "heat.updated"
EVENT_HEAT_DELETED = "heat.deleted"
EVENT_START_SCHEDULED = "start.scheduled"


# --- Durchgänge --------------------------------------------------------------


async def _booked_counts(session: AsyncSession, heat_ids: Sequence[uuid.UUID]) -> dict:
    if not heat_ids:
        return {}
    rows = await session.execute(
        select(Start.heat_id, func.count())
        .where(Start.heat_id.in_(heat_ids), Start.status != "aborted")
        .group_by(Start.heat_id)
    )
    return dict(rows.all())


async def heat_outs(session: AsyncSession, range_: Range, heats: Sequence[Heat]) -> list[HeatOut]:
    counts = await _booked_counts(session, [heat.id for heat in heats])
    return [
        HeatOut(
            id=heat.id,
            range_id=heat.range_id,
            number=heat.number,
            starts_at=heat.starts_at,
            ends_at=heat.ends_at,
            booked=counts.get(heat.id, 0),
            capacity=range_.lane_count,
        )
        for heat in heats
    ]


def _audit_heats(
    session: AsyncSession,
    actor: Actor | None,
    action: str,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    heats: Sequence[Heat],
    **extra: object,
) -> None:
    for heat in heats:
        record_audit(
            session,
            actor or Actor(),
            action,
            "heat",
            heat.id,
            {
                "tournament_id": str(tournament_id),
                "range_id": str(range_id),
                "number": heat.number,
                "starts_at": heat.starts_at.isoformat(),
                "ends_at": heat.ends_at.isoformat(),
                **extra,
            },
        )


async def _heats_of_range(session: AsyncSession, range_id: uuid.UUID) -> list[Heat]:
    rows = await session.scalars(
        select(Heat).where(Heat.range_id == range_id).order_by(Heat.starts_at, Heat.number)
    )
    return list(rows)


async def list_heats(
    session: AsyncSession, tournament_id: uuid.UUID, range_id: uuid.UUID
) -> list[HeatOut]:
    range_ = await get_range(session, tournament_id, range_id)
    return await heat_outs(session, range_, await _heats_of_range(session, range_id))


async def _get_heat(session: AsyncSession, range_id: uuid.UUID, heat_id: uuid.UUID) -> Heat:
    heat = await session.get(Heat, heat_id)
    if heat is None or heat.range_id != range_id:
        raise NotFoundError("Der Durchgang wurde auf diesem Schießstand nicht gefunden.")
    return heat


def _check_times(starts_at: datetime, ends_at: datetime) -> None:
    if ends_at <= starts_at:
        raise InputError.single("ends_at", "Ein Durchgang muss nach seinem Beginn enden.")


def _check_no_overlap(
    existing: Sequence[Heat], windows: Sequence[tuple[datetime, datetime]], own_id: uuid.UUID | None
) -> None:
    for heat in existing:
        if heat.id == own_id:
            continue
        for starts_at, ends_at in windows:
            if overlaps(heat.starts_at, heat.ends_at, starts_at, ends_at):
                raise ConflictError(
                    f"Der Durchgang überschneidet sich mit Durchgang {heat.number} auf diesem "
                    "Schießstand.",
                    field="starts_at",
                )


def _check_number_free(existing: Sequence[Heat], number: int, own_id: uuid.UUID | None) -> None:
    if any(heat.number == number and heat.id != own_id for heat in existing):
        raise ConflictError(
            f"Einen Durchgang {number} gibt es auf diesem Schießstand schon.", field="number"
        )


async def create_heat(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    data: HeatCreate,
    actor: Actor | None = None,
) -> HeatOut:
    await writable_tournament(session, tournament_id)
    range_ = await get_range(session, tournament_id, range_id, lock=True)
    _check_times(data.starts_at, data.ends_at)
    existing = await _heats_of_range(session, range_id)
    _check_no_overlap(existing, [(data.starts_at, data.ends_at)], None)
    number = data.number or max((heat.number for heat in existing), default=0) + 1
    _check_number_free(existing, number, None)
    heat = Heat(range_id=range_id, number=number, starts_at=data.starts_at, ends_at=data.ends_at)
    session.add(heat)
    await session.flush()
    _audit_heats(session, actor, "heat.created", tournament_id, range_id, [heat])
    await session.commit()
    events.publish(
        EVENT_HEAT_CREATED,
        {**event_ids(tournament_id=tournament_id, range_id=range_id), "heat_ids": [str(heat.id)]},
    )
    return (await heat_outs(session, range_, [heat]))[0]


async def create_series(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    data: HeatSeries,
    actor: Actor | None = None,
) -> list[HeatOut]:
    """Legt `count` Durchgänge ab `starts_at` an, je `heat_minutes` des Wettbewerbs lang.

    `heat_minutes` enthält die Wechselzeit schon (siehe Modul `turnier`); die Durchgänge folgen
    deshalb lückenlos aufeinander. Die Nummern schließen an die vorhandenen an.
    """
    await writable_tournament(session, tournament_id)
    range_ = await get_range(session, tournament_id, range_id, lock=True)
    competition = await session.get(Competition, data.competition_id)
    if competition is None or competition.tournament_id != tournament_id:
        raise InputError.single("competition_id", "Der Wettbewerb gehört nicht zu diesem Turnier.")
    if competition.range_id != range_id:
        raise InputError.single(
            "competition_id", "Der Wettbewerb findet nicht auf diesem Schießstand statt."
        )
    if competition.planning != "schedule" or competition.heat_minutes is None:
        raise InputError.single(
            "competition_id",
            "Der Wettbewerb wird nicht nach Zeitplan geplant oder hat keine Durchgangsdauer.",
        )
    windows = heat_series(data.starts_at, data.count, competition.heat_minutes)
    existing = await _heats_of_range(session, range_id)
    _check_no_overlap(existing, windows, None)
    first_number = max((heat.number for heat in existing), default=0) + 1
    heats = [
        Heat(range_id=range_id, number=first_number + i, starts_at=starts_at, ends_at=ends_at)
        for i, (starts_at, ends_at) in enumerate(windows)
    ]
    session.add_all(heats)
    await session.flush()
    _audit_heats(session, actor, "heat.created", tournament_id, range_id, heats)
    await session.commit()
    events.publish(
        EVENT_HEAT_CREATED,
        {
            **event_ids(tournament_id=tournament_id, range_id=range_id),
            "heat_ids": [str(heat.id) for heat in heats],
        },
    )
    return await heat_outs(session, range_, heats)


async def update_heat(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    heat_id: uuid.UUID,
    data: HeatUpdate,
    actor: Actor | None = None,
) -> HeatOut:
    await writable_tournament(session, tournament_id)
    range_ = await get_range(session, tournament_id, range_id, lock=True)
    heat = await _get_heat(session, range_id, heat_id)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None:
            raise InputError.single(key, f"Das Feld „{key}“ darf nicht leer sein.")
    starts_at = changes.get("starts_at", heat.starts_at)
    ends_at = changes.get("ends_at", heat.ends_at)
    _check_times(starts_at, ends_at)
    existing = await _heats_of_range(session, range_id)
    _check_no_overlap(existing, [(starts_at, ends_at)], heat.id)
    if "number" in changes:
        _check_number_free(existing, changes["number"], heat.id)
    # Eingeplante Personen dürfen durch die neue Zeit nicht doppelt belegt werden.
    for start in await session.scalars(
        select(Start).where(Start.heat_id == heat.id, Start.status != "aborted")
    ):
        await _check_person_free(session, start.entry_id, starts_at, ends_at, exclude_heat=heat.id)
    for key, value in changes.items():
        setattr(heat, key, value)
    _audit_heats(
        session, actor, "heat.updated", tournament_id, range_id, [heat], changed=sorted(changes)
    )
    await session.commit()
    events.publish(
        EVENT_HEAT_UPDATED,
        event_ids(tournament_id=tournament_id, range_id=range_id, heat_id=heat.id),
    )
    return (await heat_outs(session, range_, [heat]))[0]


async def delete_heat(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    heat_id: uuid.UUID,
) -> None:
    await writable_tournament(session, tournament_id)
    await get_range(session, tournament_id, range_id, lock=True)
    heat = await _get_heat(session, range_id, heat_id)
    booked = await session.scalar(
        select(func.count()).select_from(Start).where(Start.heat_id == heat.id)
    )
    if booked:
        raise ConflictError(
            f"Im Durchgang {heat.number} sind noch {booked} Start(s) eingeplant. Bitte sie erst "
            "umplanen."
        )
    record_audit(
        session,
        actor,
        "heat.deleted",
        "heat",
        heat.id,
        {"tournament_id": str(tournament_id), "range_id": str(range_id), "number": heat.number},
    )
    await session.delete(heat)
    await session.commit()
    events.publish(
        EVENT_HEAT_DELETED,
        event_ids(tournament_id=tournament_id, range_id=range_id, heat_id=heat_id),
    )


# --- Plätze ------------------------------------------------------------------


async def _check_person_free(
    session: AsyncSession,
    entry_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
    *,
    exclude_heat: uuid.UUID | None = None,
    exclude_start: uuid.UUID | None = None,
) -> None:
    """Die Person (Anmeldung) darf in keinem anderen Durchgang zur selben Zeit stehen."""
    conditions = [Start.entry_id == entry_id, Start.status != "aborted"]
    if exclude_heat is not None:
        conditions.append(Heat.id != exclude_heat)
    if exclude_start is not None:
        conditions.append(Start.id != exclude_start)
    rows = await session.execute(
        select(Heat, Range.name)
        .join(Start, Start.heat_id == Heat.id)
        .join(Range, Range.id == Heat.range_id)
        .where(*conditions)
    )
    for heat, range_name in rows:
        if overlaps(heat.starts_at, heat.ends_at, starts_at, ends_at):
            raise ConflictError(
                f"Die Person ist zur selben Zeit schon im Durchgang {heat.number} auf "
                f"„{range_name}“ eingeplant."
            )


async def _taken_lanes(
    session: AsyncSession, heat_id: uuid.UUID, exclude_start: uuid.UUID
) -> set[int]:
    rows = await session.scalars(
        select(Start.lane).where(
            Start.heat_id == heat_id, Start.status != "aborted", Start.id != exclude_start
        )
    )
    return {lane for lane in rows if lane is not None}


async def place(
    session: AsyncSession,
    start: Start,
    entry: Entry,
    competition: Competition,
    heat_id: uuid.UUID,
    lane: int | None,
) -> None:
    """Setzt einen wartenden Start auf einen Platz (Durchgang + Schützenstand). Committet nicht."""
    if competition.planning != "schedule":
        raise InputError.single(
            "heat_id",
            "Dieser Wettbewerb wird nach Reihenfolge geplant; Durchgänge gibt es nur beim "
            "Zeitplan.",
        )
    if start.status != "registered":
        raise ConflictError("Nur ein wartender Start lässt sich (um)planen.")
    if competition.range_id is None:
        raise ConflictError("Der Wettbewerb ist noch keinem Schießstand zugeordnet.")
    range_ = await get_range(session, entry.tournament_id, competition.range_id, lock=True)
    heat = await session.get(Heat, heat_id)
    if heat is None or heat.range_id != range_.id:
        raise InputError.single(
            "heat_id", "Der Durchgang gehört nicht zum Schießstand dieses Wettbewerbs."
        )
    taken = await _taken_lanes(session, heat.id, start.id)
    if lane is None:
        lane = first_free_lane(range_.lane_count, taken)
        if lane is None:
            raise ConflictError(
                f"Der Durchgang {heat.number} ist voll ({range_.lane_count} Schützenstände)."
            )
    elif lane > range_.lane_count:
        raise InputError.single(
            "lane", f"Der Schießstand hat nur {range_.lane_count} Schützenstände."
        )
    elif lane in taken:
        raise ConflictError(
            f"Schützenstand {lane} im Durchgang {heat.number} ist schon belegt.", field="lane"
        )
    await _check_person_free(
        session, entry.id, heat.starts_at, heat.ends_at, exclude_start=start.id
    )
    start.heat_id = heat.id
    start.lane = lane
    start.queue_position = None
    await session.flush()


async def assign_slot(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    heat_id: uuid.UUID,
    lane: int | None,
    actor: Actor | None = None,
) -> Start:
    await writable_tournament(session, tournament_id)
    context = await get_start(session, tournament_id, start_id)
    previous_heat = context.start.heat_id
    await place(session, context.start, context.entry, context.competition, heat_id, lane)
    heat = await session.get(Heat, heat_id)
    record_audit(
        session,
        actor or Actor(),
        "start.slot_assigned",
        "start",
        start_id,
        context.audit_details(
            heat_id=str(heat_id),
            heat_number=heat.number if heat else None,
            lane=context.start.lane,
            previous_heat_id=str(previous_heat) if previous_heat else None,
        ),
    )
    await session.commit()
    events.publish(
        EVENT_START_SCHEDULED,
        {
            **event_ids(
                tournament_id=tournament_id,
                entry_id=context.entry.id,
                start_id=start_id,
                range_id=context.competition.range_id,
                heat_id=heat_id,
            ),
            "previous_heat_id": str(previous_heat) if previous_heat else None,
        },
    )
    await session.refresh(context.start)
    return context.start


async def clear_slot(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    actor: Actor | None = None,
) -> Start:
    await writable_tournament(session, tournament_id)
    context = await get_start(session, tournament_id, start_id)
    if context.start.status != "registered":
        raise ConflictError("Nur ein wartender Start lässt sich (um)planen.")
    previous_heat = context.start.heat_id
    context.start.heat_id = None
    context.start.lane = None
    record_audit(
        session,
        actor or Actor(),
        "start.slot_cleared",
        "start",
        start_id,
        context.audit_details(previous_heat_id=str(previous_heat) if previous_heat else None),
    )
    await session.commit()
    events.publish(
        EVENT_START_SCHEDULED,
        {
            **event_ids(
                tournament_id=tournament_id,
                entry_id=context.entry.id,
                start_id=start_id,
                range_id=context.competition.range_id,
                heat_id=None,
            ),
            "previous_heat_id": str(previous_heat) if previous_heat else None,
        },
    )
    await session.refresh(context.start)
    return context.start


async def next_slot(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    competition_id: uuid.UUID,
    entry_id: uuid.UUID | None,
    after: datetime,
) -> tuple[HeatOut, int] | None:
    """Vorschlag: frühester Durchgang ab `after` mit freiem Schützenstand (für die Person ohne
    Überschneidung, wenn `entry_id` angegeben ist). None, wenn es keinen gibt."""
    await get_tournament(session, tournament_id)
    competition = await session.get(Competition, competition_id)
    if competition is None or competition.tournament_id != tournament_id:
        raise NotFoundError("Der Wettbewerb wurde in diesem Turnier nicht gefunden.")
    if competition.planning != "schedule":
        raise ConflictError("Dieser Wettbewerb wird nach Reihenfolge geplant, nicht nach Zeitplan.")
    if competition.range_id is None:
        raise ConflictError("Der Wettbewerb ist noch keinem Schießstand zugeordnet.")
    range_ = await get_range(session, tournament_id, competition.range_id)

    busy: list[tuple[datetime, datetime]] = []
    if entry_id is not None:
        entry = await get_entry(session, tournament_id, entry_id)
        rows = await session.execute(
            select(Heat.starts_at, Heat.ends_at)
            .join(Start, Start.heat_id == Heat.id)
            .where(Start.entry_id == entry.id, Start.status != "aborted")
        )
        busy = [(starts_at, ends_at) for starts_at, ends_at in rows]

    heats = [heat for heat in await _heats_of_range(session, range_.id) if heat.starts_at >= after]
    taken: dict[uuid.UUID, set[int]] = defaultdict(set)
    if heats:
        for heat_id, lane in await session.execute(
            select(Start.heat_id, Start.lane).where(
                Start.heat_id.in_([heat.id for heat in heats]), Start.status != "aborted"
            )
        ):
            if heat_id is not None and lane is not None:
                taken[heat_id].add(lane)
    for heat in heats:
        if any(overlaps(heat.starts_at, heat.ends_at, b_start, b_end) for b_start, b_end in busy):
            continue
        lane = first_free_lane(range_.lane_count, taken[heat.id])
        if lane is not None:
            return (await heat_outs(session, range_, [heat]))[0], lane
    return None


# --- Freihalten für den nächsten Durchgang -----------------------------------


HEAT_IMMINENT = "heat_imminent"


@dataclass(frozen=True, slots=True)
class Reservation:
    """Was die Durchgänge eines Schießstands gerade von seinen Schützenständen brauchen."""

    # Nächster Durchgang mit wartenden Starts, der noch nicht vorbei ist (für die Sichten).
    upcoming: HeatReservationOut | None
    # Schützenstände, die gerade für einen Durchgang freigehalten werden, mit dem frühesten davon.
    held: dict[int, Heat]
    tz: ZoneInfo

    def conflict(self, lanes: Iterable[int], now: datetime) -> CodedError:
        """409 `heat_imminent` für einen Aufruf aus der Reihenfolge auf `lanes`."""
        wanted = sorted(set(lanes))
        heat = min((self.held[lane] for lane in wanted), key=lambda item: item.starts_at)
        clock = heat.starts_at.astimezone(self.tz).strftime("%H:%M")
        when = f"beginnt um {clock} Uhr" if heat.starts_at > now else f"hat um {clock} Uhr begonnen"
        return CodedError(
            status.HTTP_409_CONFLICT,
            f"Durchgang {heat.number} {when} und braucht {lane_list(wanted)}. Soll trotzdem "
            "aus der Reihenfolge aufgerufen werden, bitte bestätigen.",
            HEAT_IMMINENT,
        )

    def held_text(self, lanes: Iterable[int]) -> str:
        wanted = sorted(set(lanes))
        heat = min((self.held[lane] for lane in wanted), key=lambda item: item.starts_at)
        clock = heat.starts_at.astimezone(self.tz).strftime("%H:%M")
        verb = "bleibt" if len(wanted) == 1 else "bleiben"
        return f"{lane_list(wanted)} {verb} für Durchgang {heat.number} ({clock} Uhr) frei."


async def heat_reservation(
    session: AsyncSession, tournament: Tournament, range_: Range, now: datetime
) -> Reservation:
    """Nächster Durchgang des Schießstands und die Schützenstände, die gerade freigehalten werden.

    Ein Durchgang hält die gebuchten Schützenstände seiner wartenden Starts frei, sobald er
    innerhalb von `heat_reserve_minutes` (Turnier-Einstellung) beginnt, bis er vorbei ist.
    """
    minutes = heat_reserve_minutes(tournament.settings or {})
    tz = zone_of(tournament.settings)
    rows = await session.execute(
        select(Heat, Start.lane)
        .join(Start, Start.heat_id == Heat.id)
        .where(Heat.range_id == range_.id, Heat.ends_at > now, Start.status == "registered")
        .order_by(Heat.starts_at, Heat.number, Start.lane)
    )
    lanes: dict[uuid.UUID, list[int]] = defaultdict(list)
    heats: dict[uuid.UUID, Heat] = {}
    for heat, lane in rows:
        heats.setdefault(heat.id, heat)
        if lane is not None:
            lanes[heat.id].append(lane)
    held: dict[int, Heat] = {}
    for heat in heats.values():
        if heat_is_reserving(heat.starts_at, heat.ends_at, now, minutes):
            for lane in lanes[heat.id]:
                held.setdefault(lane, heat)
    upcoming = None
    if heats:
        heat = next(iter(heats.values()))
        upcoming = HeatReservationOut(
            heat_id=heat.id,
            number=heat.number,
            starts_at=heat.starts_at,
            ends_at=heat.ends_at,
            lanes=sorted(set(lanes[heat.id])),
            reserve_minutes=minutes,
            reserved_from=heat.starts_at - timedelta(minutes=minutes) if minutes else None,
            active=heat_is_reserving(heat.starts_at, heat.ends_at, now, minutes),
        )
    return Reservation(upcoming=upcoming, held=held, tz=tz)


# --- Aufruf eines Durchgangs -------------------------------------------------


async def call_heat(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    heat_id: uuid.UUID,
) -> list[Start]:
    """Ruft alle wartenden Starts eines Durchgangs auf ihre Schützenstände – alle oder keinen."""
    await writable_tournament(session, tournament_id)
    await get_range(session, tournament_id, range_id, lock=True)
    heat = await _get_heat(session, range_id, heat_id)
    rows = (
        await session.execute(
            select(Start, Entry.start_number)
            .join(Entry, Entry.id == Start.entry_id)
            .where(Start.heat_id == heat.id, Start.status == "registered")
            .order_by(Start.lane)
        )
    ).all()
    if not rows:
        raise ConflictError(f"Im Durchgang {heat.number} wartet kein Start.")
    occupied = await occupied_on_range(session, range_id)
    blocked = sorted(start.lane for start, _ in rows if start.lane in occupied)
    if blocked:
        verb = "ist" if len(blocked) == 1 else "sind"
        raise ConflictError(
            f"{lane_list(blocked)} {verb} noch belegt. Bitte die laufenden Starts erst "
            "abschließen, den Schützenstand freigeben, zurückstellen oder abbrechen."
        )
    busy = await on_lane_entry_ids(session, tournament_id)
    doubled = sorted(number for start, number in rows if start.entry_id in busy)
    if doubled:
        numbers = ", ".join(str(number) for number in doubled)
        raise ConflictError(f"Startnummer {numbers} steht gerade auf einem anderen Schützenstand.")
    changes: list[StatusChange] = []
    for start, _ in rows:
        changes.append(await transition(session, start, "called", actor))
    await session.commit()
    for change in changes:
        publish_status(events, change)
    called = [start for start, _ in rows]
    for start in called:
        await session.refresh(start)
    return called
