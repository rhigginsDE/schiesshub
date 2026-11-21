"""Lesende Sichten für die Stationen: Startliste, Reihenfolge eines Stands, „am Stand“.

Diese Sichten zeigen Personen nur so, wie sie es gewählt haben (`display_mode`): voll, abgekürzt
oder gar nicht. Der volle Name erscheint hier nie, wenn die Person ihn nicht freigegeben hat;
den Verein nur mit `show_club`.
"""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.starts.common import get_range, get_tournament
from app.modules.starts.models import Entry, Heat, Start
from app.modules.starts.schedule import heat_outs
from app.modules.starts.schemas import LaneOut, QueueOut, RangeNowOut, StationStartOut
from app.modules.teilnehmer.models import Club, Person
from app.modules.teilnehmer.names import display_name
from app.modules.turnier.models import Competition, Range, TournamentClass


async def station_rows(
    session: AsyncSession, *conditions: ColumnElement[bool], order_by: tuple[Any, ...]
) -> list[StationStartOut]:
    rows = await session.execute(
        select(
            Start,
            Entry.start_number,
            Entry.class_id,
            Person,
            Club.name,
            TournamentClass.short,
            Competition.name,
            Competition.range_id,
            Heat.number,
            Heat.starts_at,
        )
        .join(Entry, Entry.id == Start.entry_id)
        .join(Person, Person.id == Entry.person_id)
        .outerjoin(Club, Club.id == Person.club_id)
        .join(TournamentClass, TournamentClass.id == Entry.class_id)
        .join(Competition, Competition.id == Start.competition_id)
        .outerjoin(Heat, Heat.id == Start.heat_id)
        .where(*conditions)
        .order_by(*order_by)
    )
    return [
        StationStartOut(
            start_id=start.id,
            entry_id=start.entry_id,
            start_number=start_number,
            display_name=display_name(person.name_enc, person.display_mode),
            club=club if person.show_club else None,
            class_id=class_id,
            class_short=class_short,
            competition_id=start.competition_id,
            competition_name=competition_name,
            range_id=range_id,
            attempt=start.attempt,
            status=start.status,
            abort_reason=start.abort_reason,
            queue_position=start.queue_position,
            lane=start.lane,
            heat_id=start.heat_id,
            heat_number=heat_number,
            heat_starts_at=heat_starts_at,
        )
        for (
            start,
            start_number,
            class_id,
            person,
            club,
            class_short,
            competition_name,
            range_id,
            heat_number,
            heat_starts_at,
        ) in rows
    ]


async def startlist(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    competition_id: uuid.UUID | None,
    range_id: uuid.UUID | None,
) -> list[StationStartOut]:
    """Alle Starts des Turniers, wahlweise eines Wettbewerbs oder Stands."""
    await get_tournament(session, tournament_id)
    conditions: list[ColumnElement[bool]] = [Entry.tournament_id == tournament_id]
    if competition_id is not None:
        conditions.append(Start.competition_id == competition_id)
    if range_id is not None:
        conditions.append(Competition.range_id == range_id)
    return await station_rows(
        session,
        *conditions,
        order_by=(
            Competition.sort,
            Competition.name,
            Heat.starts_at.asc().nulls_last(),
            Start.lane.asc().nulls_last(),
            Start.queue_position.asc().nulls_last(),
            Entry.start_number,
            Start.attempt,
        ),
    )


async def _lanes(session: AsyncSession, range_: Range) -> list[LaneOut]:
    called = {
        row.lane: row
        for row in await station_rows(
            session,
            Competition.range_id == range_.id,
            Start.status == "called",
            Start.lane.is_not(None),
            order_by=(Start.lane,),
        )
    }
    # Auch Bahnen über der aktuellen Bahnzahl, falls dort noch jemand steht.
    numbers = sorted(set(range(1, range_.lane_count + 1)) | {lane for lane in called if lane})
    return [LaneOut(lane=lane, start=called.get(lane)) for lane in numbers]


async def _waiting(session: AsyncSession, range_id: uuid.UUID) -> list[StationStartOut]:
    return await station_rows(
        session,
        Competition.range_id == range_id,
        Competition.planning == "queue",
        Start.status == "registered",
        Start.heat_id.is_(None),
        order_by=(Start.queue_position.asc().nulls_last(), Start.created_at, Start.attempt),
    )


async def queue_view(
    session: AsyncSession, tournament_id: uuid.UUID, range_id: uuid.UUID
) -> QueueOut:
    range_ = await get_range(session, tournament_id, range_id)
    return QueueOut(
        range_id=range_.id,
        lane_count=range_.lane_count,
        waiting=await _waiting(session, range_.id),
        lanes=await _lanes(session, range_),
    )


async def range_now(
    session: AsyncSession, tournament_id: uuid.UUID, range_id: uuid.UUID
) -> RangeNowOut:
    """„Am Stand“ (aufgerufene Starts je Bahn) und „als Nächstes“ (Durchgang und Reihenfolge)."""
    range_ = await get_range(session, tournament_id, range_id)
    next_heat = await session.scalar(
        select(Heat)
        .where(
            Heat.range_id == range_.id,
            Heat.id.in_(select(Start.heat_id).where(Start.status == "registered")),
        )
        .order_by(Heat.starts_at, Heat.number)
        .limit(1)
    )
    heat_starts: list[StationStartOut] = []
    if next_heat is not None:
        heat_starts = await station_rows(
            session,
            Start.heat_id == next_heat.id,
            Start.status == "registered",
            order_by=(Start.lane,),
        )
    waiting = await _waiting(session, range_.id)
    return RangeNowOut(
        range_id=range_.id,
        lane_count=range_.lane_count,
        lanes=await _lanes(session, range_),
        next_heat=(await heat_outs(session, range_, [next_heat]))[0] if next_heat else None,
        next_heat_starts=heat_starts,
        next_queue=waiting[: range_.lane_count],
    )
