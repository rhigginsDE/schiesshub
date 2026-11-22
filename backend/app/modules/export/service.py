"""Datenbeschaffung für die Listen über die Sichten der Module `starts` und `ergebnisse`.

Rangfolge, Gleichstand, Mehrfachstart und Klassen rechnet die Rangliste des Moduls `ergebnisse`
(`ranking.competition_ranking`); die Startliste kommt aus `starts.views.startlist`. Beide zeigen
Personen nur nach ihrer Anzeige-Einstellung. Für `names=full` liest dieses Modul zusätzlich den
vollen Namen und den Verein je Anmeldung nach – das darf nur, wer `export.full_names` hat (prüft
der Router).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ergebnisse import ranking
from app.modules.ergebnisse.models import ResultCurrent
from app.modules.ergebnisse.recompute import ensure_current
from app.modules.ergebnisse.service import competition_of, is_provisional, server_now
from app.modules.export import tables
from app.modules.export.records import (
    CompetitionInfo,
    Meta,
    NamesMode,
    PersonName,
    ResultRecord,
    SeriesValue,
    StartRecord,
    WinnerSection,
)
from app.modules.starts import views
from app.modules.starts.common import NotFoundError, get_range, get_tournament
from app.modules.starts.models import Entry
from app.modules.starts.schemas import StationStartOut
from app.modules.teilnehmer.models import Club, Person
from app.modules.teilnehmer.names import clean_text
from app.modules.turnier.models import Competition, Range, TournamentClass
from app.scoring import ComputedResult


async def meta(session: AsyncSession, tournament_id: uuid.UUID, names: NamesMode) -> Meta:
    tournament = await get_tournament(session, tournament_id)
    return Meta(
        tournament_name=tournament.name,
        organizer=tournament.organizer,
        date_from=tournament.date_from,
        date_to=tournament.date_to,
        generated_at=await server_now(session),
        names=names,
    )


def _sections_of(definition: dict | None) -> tuple[tuple[str, str], ...]:
    variant = (definition or {}).get("variant") or {}
    return tuple(
        (str(section.get("id")), str(section.get("name") or section.get("id")))
        for section in variant.get("abschnitte") or []
        if isinstance(section, dict) and section.get("id")
    )


async def competitions(
    session: AsyncSession, tournament_id: uuid.UUID
) -> dict[uuid.UUID, CompetitionInfo]:
    ranges = {
        item.id: item
        for item in await session.scalars(select(Range).where(Range.tournament_id == tournament_id))
    }
    result = {}
    for competition in await session.scalars(
        select(Competition)
        .where(Competition.tournament_id == tournament_id)
        .order_by(Competition.sort, Competition.name)
    ):
        range_ = ranges.get(competition.range_id) if competition.range_id else None
        result[competition.id] = CompetitionInfo(
            id=competition.id,
            code=competition.catalog_code,
            name=competition.name,
            sort=competition.sort,
            range_id=competition.range_id,
            range_name=range_.name if range_ else None,
            range_sort=range_.sort if range_ else None,
            multi_start=competition.multi_start,
            planning=competition.planning,
            sections=_sections_of(competition.definition),
        )
    return result


async def class_names(session: AsyncSession, tournament_id: uuid.UUID) -> dict[uuid.UUID, str]:
    return dict(
        (
            await session.execute(
                select(TournamentClass.id, TournamentClass.name).where(
                    TournamentClass.tournament_id == tournament_id
                )
            )
        ).all()
    )


async def check_class(
    session: AsyncSession, tournament_id: uuid.UUID, class_id: uuid.UUID | None
) -> None:
    if class_id is None:
        return
    klass = await session.get(TournamentClass, class_id)
    if klass is None or klass.tournament_id != tournament_id:
        raise NotFoundError("Die Klasse wurde in diesem Turnier nicht gefunden.")


async def full_names(
    session: AsyncSession, tournament_id: uuid.UUID
) -> dict[uuid.UUID, PersonName]:
    """Voller Name und Verein je Anmeldung, unabhängig von der Anzeige-Einstellung."""
    rows = await session.execute(
        select(Entry.id, Person.name_enc, Club.name)
        .join(Person, Person.id == Entry.person_id)
        .outerjoin(Club, Club.id == Person.club_id)
        .where(Entry.tournament_id == tournament_id)
    )
    return {entry_id: PersonName(clean_text(name), club) for entry_id, name, club in rows}


async def _names(
    session: AsyncSession, tournament_id: uuid.UUID, names: NamesMode
) -> dict[uuid.UUID, PersonName] | None:
    return await full_names(session, tournament_id) if names == "full" else None


def _start_record(
    start: StationStartOut,
    competitions_: dict[uuid.UUID, CompetitionInfo],
    classes: dict[uuid.UUID, str],
    names: dict[uuid.UUID, PersonName] | None,
) -> StartRecord:
    return StartRecord(
        start_id=start.start_id,
        entry_id=start.entry_id,
        start_number=start.start_number,
        person=tables.person_for(start.entry_id, start.display_name, start.club, names),
        class_id=start.class_id,
        class_short=start.class_short,
        class_name=classes.get(start.class_id, start.class_short),
        competition=competitions_[start.competition_id],
        attempt=start.attempt,
        status=start.status,
        abort_reason=start.abort_reason,
        queue_position=start.queue_position,
        heat_number=start.heat_number,
        heat_starts_at=start.heat_starts_at,
        lane=start.lane,
    )


async def startlist(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    *,
    competition_id: uuid.UUID | None,
    range_id: uuid.UUID | None,
    names: NamesMode,
) -> list[StartRecord]:
    await get_tournament(session, tournament_id)
    if competition_id is not None:
        await competition_of(session, tournament_id, competition_id)
    if range_id is not None:
        await get_range(session, tournament_id, range_id)
    starts = await views.startlist(session, tournament_id, competition_id, range_id)
    competitions_ = await competitions(session, tournament_id)
    classes = await class_names(session, tournament_id)
    lookup = await _names(session, tournament_id, names)
    return [_start_record(start, competitions_, classes, lookup) for start in starts]


async def winners(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    *,
    competition_id: uuid.UUID | None,
    class_id: uuid.UUID | None,
    top: int | None,
    merged: bool,
    include_provisional: bool,
    names: NamesMode,
) -> list[WinnerSection]:
    await get_tournament(session, tournament_id)
    if competition_id is not None:
        await competition_of(session, tournament_id, competition_id)
    await check_class(session, tournament_id, class_id)
    competitions_ = await competitions(session, tournament_id)
    classes = await class_names(session, tournament_id)
    lookup = await _names(session, tournament_id, names)
    chosen: Sequence[uuid.UUID] = (
        [competition_id] if competition_id is not None else list(competitions_)
    )
    sections = []
    for cid in chosen:
        result = await ranking.competition_ranking(
            session,
            tournament_id,
            cid,
            class_id=class_id,
            include_provisional=include_provisional,
            scope="final",
            merged=merged,
        )
        aborted = [
            start
            for start in await views.startlist(session, tournament_id, cid, None)
            if start.status == "aborted"
        ]
        found = tables.winner_tables(
            result, aborted, class_names=classes, top=top, class_id=class_id, full_names=lookup
        )
        if competition_id is None and not any(table.rows for table in found):
            # Über alle Wettbewerbe: solche ohne jedes Ergebnis weglassen.
            continue
        sections.append(tables.winner_section(competitions_[cid], result.unit, found))
    return sections


def _series(computed: ComputedResult | None) -> tuple[SeriesValue, ...]:
    if computed is None:
        return ()
    return tuple(
        SeriesValue(
            section_id=section.id,
            number=series.number,
            struck=series.struck,
            status=series.status,
            rings=series.rings,
            time_cs=series.time_cs,
            standing=series.standing,
            total_cs=series.total_cs,
        )
        for section in computed.sections
        for series in section.series
    )


async def results(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    *,
    competition_id: uuid.UUID | None,
    names: NamesMode,
) -> list[ResultRecord]:
    """Je Start eine Zeile mit dem aktuellen Stand (auch ohne Ergebnis, dann leer)."""
    starts = await startlist(
        session, tournament_id, competition_id=competition_id, range_id=None, names=names
    )
    for competition in await session.scalars(
        select(Competition).where(Competition.tournament_id == tournament_id)
    ):
        # Nach einer Änderung der Wertung erst nachziehen (wie die Ranglisten).
        await ensure_current(session, competition)
    now = await server_now(session)
    ids = [start.start_id for start in starts]
    currents = {
        current.start_id: current
        for current in await session.scalars(
            select(ResultCurrent).where(ResultCurrent.start_id.in_(ids))
        )
    }
    records = []
    for start in starts:
        current = currents.get(start.start_id)
        computed = (
            ComputedResult.model_validate(current.computed)
            if current is not None and current.computed is not None
            else None
        )
        records.append(
            ResultRecord(
                start=start,
                has_result=computed is not None,
                score=computed.score if computed is not None else None,
                unit=computed.unit if computed is not None else None,
                complete=computed.complete if computed is not None else False,
                tens=computed.tens if computed is not None else None,
                inner_tens=computed.inner_tens if computed is not None else None,
                finalized_at=current.finalized_at if current is not None else None,
                provisional_until=current.provisional_until if current is not None else None,
                is_provisional=is_provisional(current, now),
                needs_review=bool(current is not None and current.needs_review),
                series=_series(computed),
            )
        )
    return sorted(
        records,
        key=lambda r: (
            r.start.competition.sort,
            r.start.competition.name,
            str(r.start.competition.id),
            r.start.start_number,
            r.start.attempt,
        ),
    )
