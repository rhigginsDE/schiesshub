"""Reihenfolge am Stand: Verschieben, Aufrufen, Zurückstellen, „nächste aufrufen“, Bahn freigeben.

Die Reihenfolge gehört zum Stand: Alle wartenden Starts der Wettbewerbe mit Planung `queue` auf
einem Stand stehen in einer Liste (`queue_position`, lückenlos ab 1). Die Bahnbelegung teilt sie
mit den Durchgängen des Zeitplans. Alle Vorgänge sperren den Stand und laufen so nacheinander.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InputError
from app.core.events import EventHub
from app.core.security import Actor
from app.modules.auth.audit import record_audit
from app.modules.starts.common import (
    ConflictError,
    StartContext,
    event_ids,
    get_range,
    get_start,
    occupied_on_range,
    on_lane_entry_ids,
    renumber_queue,
    waiting_starts,
    writable_tournament,
)
from app.modules.starts.lifecycle import StatusChange, publish_status, transition
from app.modules.starts.models import Entry, Start
from app.modules.starts.rules import (
    RuleError,
    Waiting,
    distribute_lanes,
    first_free_lane,
    move_to,
)
from app.modules.starts.schedule import heat_reservation
from app.modules.starts.schemas import HeatReservationOut, MoveRequest, SkippedStartOut
from app.modules.turnier.models import Range

EVENT_START_MOVED = "start.moved"
EVENT_LANE_RELEASED = "start.lane_released"


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
    actor: Actor | None = None,
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
    record_audit(
        session,
        actor or Actor(),
        "start.moved",
        "start",
        start_id,
        context.audit_details(
            range_id=str(range_.id),
            from_position=order.index(start_id) + 1,
            position=new_order.index(start_id) + 1,
        ),
    )
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
    if entry.id in await on_lane_entry_ids(session, tournament_id):
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
    *,
    confirm_heat_conflict: bool = False,
) -> Start:
    """Ruft einen Start auf eine Bahn: Reihenfolge auf `lane` (oder die erste freie),
    Zeitplan auf die Bahn seines Durchgangs.

    Aus der Reihenfolge nie ohne Bestätigung auf eine Bahn, die ein bald beginnender Durchgang
    braucht (409 `heat_imminent`); ohne Bahnangabe zuerst auf eine Bahn, die keiner braucht.
    """
    tournament = await writable_tournament(session, tournament_id)
    context = await get_start(session, tournament_id, start_id)
    if context.competition.range_id is None:
        raise ConflictError("Der Wettbewerb ist noch keinem Stand zugeordnet.")
    range_ = await get_range(session, tournament_id, context.competition.range_id, lock=True)
    start = context.start
    if start.status != "registered":
        raise ConflictError("Nur ein wartender Start lässt sich aufrufen.")
    occupied = await occupied_on_range(session, range_.id)
    now = datetime.now(UTC)
    held: set[int] = set()
    reservation = None
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
    else:
        if not confirm_heat_conflict:
            reservation = await heat_reservation(session, tournament, range_, now)
            held = set(reservation.held)
        if lane is None:
            lane = first_free_lane(range_.lane_count, set(occupied) | held)
            if lane is None:
                free = [n for n in range(1, range_.lane_count + 1) if n not in occupied]
                if not free:
                    raise ConflictError("Alle Bahnen des Stands sind belegt.")
                assert reservation is not None
                raise reservation.conflict(free, now)
        elif lane > range_.lane_count:
            raise InputError.single("lane", f"Der Stand hat nur {range_.lane_count} Bahnen.")
    assert lane is not None
    if lane in occupied:
        raise ConflictError(f"Bahn {lane} ist schon belegt.", field="lane")
    if lane in held:
        assert reservation is not None
        raise reservation.conflict([lane], now)
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
    record_audit(
        session,
        actor,
        "start.returned",
        "start",
        start.id,
        context.audit_details(range_id=str(range_.id), lane=start.lane, position=position),
    )
    await session.commit()
    publish_status(events, change)
    await session.refresh(start)
    return start


@dataclass(slots=True)
class CallNextResult:
    called: list[Start]
    skipped: list[SkippedStartOut]
    held_lanes: list[int]
    upcoming_heat: HeatReservationOut | None
    message: str | None


def _skipped_text(numbers: list[int]) -> str:
    if len(numbers) == 1:
        return f"Startnummer {numbers[0]} steht gerade auf einer Bahn und wurde übersprungen."
    listed = ", ".join(str(number) for number in numbers[:-1])
    return (
        f"Startnummern {listed} und {numbers[-1]} stehen gerade auf einer Bahn und wurden "
        "übersprungen."
    )


async def _start_numbers(session: AsyncSession, entry_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not entry_ids:
        return {}
    rows = await session.execute(
        select(Entry.id, Entry.start_number).where(Entry.id.in_(entry_ids))
    )
    return dict(rows.all())


async def call_next(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    lane: int | None = None,
    *,
    confirm_heat_conflict: bool = False,
) -> CallNextResult:
    """Füllt die freien Bahnen (oder nur `lane`) der Reihe nach aus der Reihenfolge.

    Wer gerade auf einer Bahn steht (auch an einem anderen Stand), wird übersprungen und behält
    seinen Platz. Bahnen, die ein bald beginnender Durchgang braucht, bleiben ohne Bestätigung
    frei; wäre nur auf ihnen jemand drangekommen, kommt 409 `heat_imminent`.
    """
    tournament = await writable_tournament(session, tournament_id)
    range_ = await get_range(session, tournament_id, range_id, lock=True)
    occupied = await occupied_on_range(session, range_.id)
    if lane is not None:
        if lane > range_.lane_count:
            raise InputError.single("lane", f"Der Stand hat nur {range_.lane_count} Bahnen.")
        if lane in occupied:
            raise ConflictError(f"Bahn {lane} ist schon belegt.", field="lane")
        free = [lane]
    else:
        free = [number for number in range(1, range_.lane_count + 1) if number not in occupied]
    now = datetime.now(UTC)
    reservation = await heat_reservation(session, tournament, range_, now)
    held = [] if confirm_heat_conflict else [n for n in free if n in reservation.held]
    usable = [number for number in free if number not in held]
    waiting = await renumber_queue(session, range_.id)
    by_id = {start.id: start for start in waiting}
    candidates = [Waiting(start_id=start.id, entry_id=start.entry_id) for start in waiting]
    busy = await on_lane_entry_ids(session, tournament_id)
    distribution = distribute_lanes(usable, candidates, busy)
    # Wer auf den freigehaltenen Bahnen noch drangekommen wäre („der Rest“).
    picked = {start_id for start_id, _ in distribution.picks}
    rest = distribute_lanes(
        held,
        [candidate for candidate in candidates if candidate.start_id not in picked],
        busy | {by_id[start_id].entry_id for start_id in picked},
    )
    held_lanes = sorted(number for _, number in rest.picks)
    if held_lanes and not distribution.picks:
        raise reservation.conflict(held_lanes, now)

    changes: list[StatusChange] = []
    for start_id, number in distribution.picks:
        by_id[start_id].lane = number
        changes.append(await transition(session, by_id[start_id], "called", actor))
    numbers = await _start_numbers(
        session, [by_id[start_id].entry_id for start_id in distribution.skipped]
    )
    skipped = [
        SkippedStartOut(
            start_id=start_id,
            entry_id=by_id[start_id].entry_id,
            start_number=numbers[by_id[start_id].entry_id],
            competition_id=by_id[start_id].competition_id,
            queue_position=by_id[start_id].queue_position,
            reason="on_lane",
        )
        for start_id in distribution.skipped
    ]
    await session.commit()
    for change in changes:
        publish_status(events, change)
    called = [by_id[start_id] for start_id, _ in distribution.picks]
    for start in called:
        await session.refresh(start)
    texts = []
    if skipped:
        texts.append(_skipped_text(sorted({item.start_number for item in skipped})))
    if held_lanes:
        texts.append(reservation.held_text(held_lanes))
    return CallNextResult(
        called=called,
        skipped=skipped,
        held_lanes=held_lanes,
        upcoming_heat=reservation.upcoming,
        message=" ".join(texts) or None,
    )


async def release_lane(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
) -> Start:
    """Gibt die Bahn eines erfassten Starts frei, ohne den Status zu ändern.

    Für den Fall, dass der Schütze fertig ist, das Ergebnis aber noch nicht abgeschlossen wird
    (z. B. Trefferaufnahme dauert). Ein nur aufgerufener Start wird zurückgestellt, nicht
    freigegeben.
    """
    context, range_ = await _context_on_range(session, tournament_id, start_id)
    start = context.start
    if not start.on_lane:
        raise ConflictError("Der Start steht auf keiner Bahn.")
    if start.status == "called":
        raise ConflictError(
            "Der Start ist nur aufgerufen und hat noch keine Eingabe. Um die Bahn frei zu "
            "machen, bitte zurückstellen oder abbrechen."
        )
    lane = start.lane
    start.on_lane = False
    record_audit(
        session,
        actor,
        "start.lane_released",
        "start",
        start.id,
        context.audit_details(range_id=str(range_.id), lane=lane),
    )
    await session.commit()
    events.publish(
        EVENT_LANE_RELEASED,
        {
            **event_ids(
                tournament_id=tournament_id,
                entry_id=context.entry.id,
                start_id=start.id,
                competition_id=context.competition.id,
                range_id=range_.id,
            ),
            "lane": lane,
        },
    )
    await session.refresh(start)
    return start
