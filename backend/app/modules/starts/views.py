"""Lesende Sichten für die Stationen: Startliste, Reihenfolge eines Schießstands,
„am Schießstand“.

Diese Sichten zeigen Personen nur so, wie sie es gewählt haben (`display_mode`): voll, abgekürzt
oder gar nicht. Der volle Name erscheint hier nie, wenn die Person ihn nicht freigegeben hat;
den Verein nur mit `show_club`. Nur mit `full_names=True` (der Router prüft die Berechtigung)
kommen zusätzlich `full_name` und `full_club` dazu, bei abgebrochenen Starts außerdem die
Bemerkung zum Abbruch (`abort_note`, über `hooks.abort_notes`); die öffentlichen Felder bleiben
gleich.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.starts import hooks
from app.modules.starts.common import get_range, get_tournament
from app.modules.starts.models import Entry, Heat, Start
from app.modules.starts.schedule import heat_outs, heat_reservation
from app.modules.starts.schemas import LaneOut, QueueOut, RangeNowOut, StationStartOut
from app.modules.teilnehmer.models import Club, Person
from app.modules.teilnehmer.names import clean_text, display_name
from app.modules.turnier.models import Competition, Range, TournamentClass


async def station_rows(
    session: AsyncSession,
    *conditions: ColumnElement[bool],
    order_by: tuple[Any, ...],
    full_names: bool = False,
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
            Competition.catalog_code,
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
    result = [
        StationStartOut(
            start_id=start.id,
            entry_id=start.entry_id,
            start_number=start_number,
            display_name=display_name(person.name_enc, person.display_mode),
            club=club if person.show_club else None,
            full_name=clean_text(person.name_enc) if full_names else None,
            full_club=club if full_names else None,
            class_id=class_id,
            class_short=class_short,
            competition_id=start.competition_id,
            competition_name=competition_name,
            competition_code=competition_code,
            range_id=range_id,
            attempt=start.attempt,
            status=start.status,
            abort_reason=start.abort_reason,
            queue_position=start.queue_position,
            lane=start.lane,
            on_lane=start.on_lane,
            called_at=start.called_at,
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
            competition_code,
            range_id,
            heat_number,
            heat_starts_at,
        ) in rows
    ]
    if full_names:
        # Bemerkung zum Abbruch nur für die Bedienung, wie der volle Name.
        aborted = [row.start_id for row in result if row.status == "aborted"]
        notes = await hooks.abort_notes(session, aborted)
        for row in result:
            row.abort_note = notes.get(row.start_id)
    return result


async def startlist(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    competition_id: uuid.UUID | None,
    range_id: uuid.UUID | None,
    *,
    full_names: bool = False,
) -> list[StationStartOut]:
    """Alle Starts des Turniers, wahlweise eines Wettbewerbs oder Schießstands.

    Reihenfolge je Wettbewerb: Durchgang (Uhrzeit, darin der gebuchte Schützenstand), sonst Platz
    in der Reihenfolge, dann Startnummer und Versuch. Der Schützenstand eines Starts ohne Durchgang
    ist nur der zuletzt benutzte und zählt nicht – sonst stünde ein 2. Versuch vor dem 1.
    """
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
            case((Start.heat_id.is_not(None), Start.lane)).asc().nulls_last(),
            Start.queue_position.asc().nulls_last(),
            Entry.start_number,
            Start.attempt,
        ),
        full_names=full_names,
    )


async def _lanes(
    session: AsyncSession, range_: Range, *, full_names: bool = False
) -> list[LaneOut]:
    """Alle Schützenstände des Schießstands; belegt ist einer, solange ein Start darauf steht
    (aufgerufen oder erfasst, noch nicht freigegeben), mit seinem Erfassungsfortschritt."""
    occupied = {
        row.lane: row
        for row in await station_rows(
            session,
            Competition.range_id == range_.id,
            Start.on_lane,
            order_by=(Start.lane,),
            full_names=full_names,
        )
    }
    progress = await hooks.lane_progress(session, [row.start_id for row in occupied.values()])
    # Auch Schützenstände über der aktuellen Zahl, falls dort noch jemand steht.
    numbers = sorted(set(range(1, range_.lane_count + 1)) | {lane for lane in occupied if lane})
    lanes = []
    for lane in numbers:
        start = occupied.get(lane)
        lanes.append(
            LaneOut(
                lane=lane,
                start=start,
                progress=progress.get(start.start_id) if start is not None else None,
            )
        )
    return lanes


async def _waiting(
    session: AsyncSession, range_id: uuid.UUID, *, full_names: bool = False
) -> list[StationStartOut]:
    return await station_rows(
        session,
        Competition.range_id == range_id,
        Competition.planning == "queue",
        Start.status == "registered",
        Start.heat_id.is_(None),
        order_by=(Start.queue_position.asc().nulls_last(), Start.created_at, Start.attempt),
        full_names=full_names,
    )


async def queue_view(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    *,
    full_names: bool = False,
) -> QueueOut:
    tournament = await get_tournament(session, tournament_id)
    range_ = await get_range(session, tournament_id, range_id)
    reservation = await heat_reservation(session, tournament, range_, datetime.now(UTC))
    return QueueOut(
        range_id=range_.id,
        lane_count=range_.lane_count,
        waiting=await _waiting(session, range_.id, full_names=full_names),
        lanes=await _lanes(session, range_, full_names=full_names),
        upcoming_heat=reservation.upcoming,
    )


async def range_now(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    *,
    full_names: bool = False,
) -> RangeNowOut:
    """„Am Schießstand“ (belegte Schützenstände mit Start und Fortschritt) und „als Nächstes“
    (Durchgang und Reihenfolge)."""
    tournament = await get_tournament(session, tournament_id)
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
            full_names=full_names,
        )
    waiting = await _waiting(session, range_.id, full_names=full_names)
    return RangeNowOut(
        range_id=range_.id,
        lane_count=range_.lane_count,
        lanes=await _lanes(session, range_, full_names=full_names),
        next_heat=(await heat_outs(session, range_, [next_heat]))[0] if next_heat else None,
        next_heat_starts=heat_starts,
        next_queue=waiting[: range_.lane_count],
        upcoming_heat=(
            await heat_reservation(session, tournament, range_, datetime.now(UTC))
        ).upcoming,
    )
