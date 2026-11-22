"""Reihenfolge am Stand: Verschieben, Aufrufen, Zurückstellen, „nächste aufrufen“.

Die Reihenfolge gehört zum Stand: Alle wartenden Starts der Wettbewerbe mit Planung `queue` auf
einem Stand stehen in einer Liste (`queue_position`, lückenlos ab 1). Die Bahnbelegung teilt sie
mit den Durchgängen des Zeitplans. Alle Vorgänge sperren den Stand und laufen so nacheinander.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InputError
from app.core.events import EventHub
from app.core.security import Actor
from app.modules.starts.common import (
    ConflictError,
    StartContext,
    called_entry_ids,
    called_on_range,
    event_ids,
    get_range,
    get_start,
    renumber_queue,
    waiting_starts,
    writable_tournament,
)
from app.modules.starts.lifecycle import StatusChange, publish_status, transition
from app.modules.starts.models import Entry, Start
from app.modules.starts.rules import RuleError, Waiting, first_free_lane, move_to, pick_for_lanes
from app.modules.starts.schemas import MoveRequest
from app.modules.turnier.models import Range

EVENT_START_MOVED = "start.moved"


async def _context_on_range(
    session: AsyncSession, tournament_id: uuid.UUID, start_id: uuid.UUID
) -> tuple[StartContext, Range]:
    await writable_tournament(session, tournament_id)
    context = await get_start(session, tournament_id, start_id)
    if context.competition.range_id is None:
        raise ConflictError("Der Wettbewerb ist noch keinem Stand zugeordnet.")
    range_ = await get_range(session, tournament_id, context.competition.range_id, lock=True)
    return context, range_


async def move(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    data: MoveRequest,
) -> uuid.UUID:
    """Verschiebt einen wartenden Start; liefert den Stand."""
    context, range_ = await _context_on_range(session, tournament_id, start_id)
    order = [start.id for start in await renumber_queue(session, range_.id)]
    if start_id not in order:
        raise ConflictError("Der Start wartet nicht in der Reihenfolge dieses Stands.")
    if data.position is not None:
        target = data.position
    else:
        current = order.index(start_id) + 1
        target = current - 1 if data.direction == "up" else current + 1
        target = min(max(target, 1), len(order))
    try:
        new_order = move_to(order, start_id, target)
    except RuleError as exc:
        raise InputError.single("position", str(exc)) from exc
    by_id = {start.id: start for start in await waiting_starts(session, range_.id)}
    for position, item in enumerate(new_order, start=1):
        by_id[item].queue_position = position
    await session.commit()
    events.publish(
        EVENT_START_MOVED,
        event_ids(
            tournament_id=tournament_id,
            range_id=range_.id,
            start_id=start_id,
            entry_id=context.entry.id,
        ),
    )
    return range_.id


async def _check_entry_free(session: AsyncSession, tournament_id: uuid.UUID, entry: Entry) -> None:
    if entry.id in await called_entry_ids(session, tournament_id):
        raise ConflictError(
            f"Startnummer {entry.start_number} steht gerade schon auf einer Bahn. Eine Person "
            "kann nicht auf zwei Bahnen zugleich stehen."
        )


async def call(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    lane: int | None,
) -> Start:
    """Ruft einen Start auf eine Bahn: Reihenfolge auf `lane` (oder die erste freie),
    Zeitplan auf die Bahn seines Durchgangs."""
    context, range_ = await _context_on_range(session, tournament_id, start_id)
    start = context.start
    if start.status != "registered":
        raise ConflictError("Nur ein wartender Start lässt sich aufrufen.")
    occupied = await called_on_range(session, range_.id)
    if context.competition.planning == "schedule":
        if start.heat_id is None:
            raise ConflictError(
                "Der Start ist noch keinem Durchgang zugewiesen. Bitte zuerst einplanen."
            )
        if lane is not None and lane != start.lane:
            raise InputError.single(
                "lane",
                f"Der Start ist im Durchgang auf Bahn {start.lane} eingeplant; zum Wechsel der "
                "Bahn bitte umplanen.",
            )
        lane = start.lane
    elif lane is None:
        lane = first_free_lane(range_.lane_count, occupied)
        if lane is None:
            raise ConflictError("Alle Bahnen des Stands sind belegt.")
    elif lane > range_.lane_count:
        raise InputError.single("lane", f"Der Stand hat nur {range_.lane_count} Bahnen.")
    assert lane is not None
    if lane in occupied:
        raise ConflictError(f"Bahn {lane} ist schon belegt.")
    await _check_entry_free(session, tournament_id, context.entry)
    start.lane = lane
    change = await transition(session, start, "called", actor)
    await session.commit()
    publish_status(events, change)
    await session.refresh(start)
    return start


async def return_start(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    position: str,
) -> Start:
    """Zurückstellen: `called → registered`. Bei der Reihenfolge vorn oder hinten einreihen;
    ein Start aus einem Durchgang behält seinen Platz im Durchgang."""
    context, range_ = await _context_on_range(session, tournament_id, start_id)
    start = context.start
    if start.status != "called":
        raise ConflictError("Nur ein aufgerufener Start lässt sich zurückstellen.")
    change = await transition(session, start, "registered", actor)
    if context.competition.planning == "queue" and start.heat_id is None and position == "front":
        waiting = await waiting_starts(session, range_.id)
        order = [start, *(other for other in waiting if other.id != start.id)]
        for number, item in enumerate(order, start=1):
            item.queue_position = number
    await session.commit()
    publish_status(events, change)
    await session.refresh(start)
    return start


async def call_next(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
) -> list[Start]:
    """Füllt alle freien Bahnen der Reihe nach aus der Reihenfolge.

    Wer gerade auf einer Bahn steht, wird übersprungen und behält seinen Platz.
    """
    await writable_tournament(session, tournament_id)
    range_ = await get_range(session, tournament_id, range_id, lock=True)
    occupied = await called_on_range(session, range_.id)
    free = [lane for lane in range(1, range_.lane_count + 1) if lane not in occupied]
    waiting = await renumber_queue(session, range_.id)
    picks = pick_for_lanes(
        free,
        [Waiting(start_id=start.id, entry_id=start.entry_id) for start in waiting],
        await called_entry_ids(session, tournament_id),
    )
    by_id = {start.id: start for start in waiting}
    changes: list[StatusChange] = []
    for start_id, lane in picks:
        by_id[start_id].lane = lane
        changes.append(await transition(session, by_id[start_id], "called", actor))
    await session.commit()
    for change in changes:
        publish_status(events, change)
    called = [by_id[start_id] for start_id, _ in picks]
    for start in called:
        await session.refresh(start)
    return called
