"""Übungsturnier mit Beispieldaten (`POST /tournaments/practice`) und sein Entfernen.

Die Beispieldaten stehen in `practice.yaml`: Stände, Wettbewerbe (Kennziffern aus dem Katalog),
erfundene Vereine und Personen, Starts mit Zielzustand und Rohwerten. Angelegt wird alles über
die echten Services der Module `turnier`, `teilnehmer`, `starts` und `ergebnisse`: Wertung,
Ranglisten, Audit- und Ereignisprotokoll sind dieselben wie in einem echten Turnier.

Kennzeichnung: Das Turnier hat `is_practice` (höchstens eines, fest ab dem Anlegen). Die Personen
tragen die Mitgliedsnummer `ÜBUNG-<n>`, ihre Vereine heißen erkennbar erfunden. Welche Personen
und Vereine die Übung angelegt hat, steht in `tournament.practice_data`.

Entfernen (`DELETE /tournaments/{id}` beim Übungsturnier, in jedem Status): Ergebnis-Ereignisse,
aktuelle Ergebnisse, Starts, Anmeldungen, Durchgänge, das Turnier, seine Audit-Einträge sowie die
Übungspersonen und -vereine. `result_event` bleibt dabei unveränderlich im Sinne der Datenbank:
Der Trigger lässt DELETE nur für Starts eines Übungsturniers zu (Migration `0016_turnier_uebung`).
Übungspersonen, die inzwischen auch in einem echten Turnier gemeldet sind, und Vereine, denen
inzwischen echte Personen angehören, bleiben stehen.

Die Module `teilnehmer`, `starts` und `ergebnisse` bauen auf `turnier` auf. Damit beim Laden
kein Kreis entsteht, werden ihre Services erst in den Funktionen importiert.
"""

import math
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventHub
from app.core.security import Actor
from app.modules.auth.audit import record_audit
from app.modules.auth.models import AuditLog
from app.modules.turnier import service
from app.modules.turnier.models import Competition, Tournament, TournamentClass
from app.modules.turnier.schemas import Name, PositiveInt, TournamentCreate, TournamentSettings
from app.modules.turnier.tournament_templates import (
    Key,
    TournamentTemplate,
    _FileModel,
    build_from_template,
    read_template_file,
)

PRACTICE_FILE = Path(__file__).parent / "practice.yaml"
MEMBER_NO_PREFIX = "ÜBUNG-"
StartState = Literal["registered", "called", "captured", "final", "aborted"]
# Diese Zustände lassen den Start auf seiner Bahn stehen; sie kommen zuletzt dran.
ON_LANE_STATES = frozenset({"called", "captured"})
# {<abschnitt>: [<serie>, …]}
RawSections = dict[str, list[dict[str, Any]]]


class PracticeExistsError(Exception):
    def __init__(self, tournament: Tournament) -> None:
        super().__init__(
            f"Es gibt schon ein Übungsturnier („{tournament.name}“). Bitte erst dieses öffnen "
            "oder entfernen."
        )
        self.tournament_id = tournament.id


# --- Datei --------------------------------------------------------------------------


class PracticeHeats(_FileModel):
    competition: Key
    count: PositiveInt
    # Beginn des ersten Durchgangs in Minuten ab jetzt (auf 5 Minuten abgerundet).
    first_offset_minutes: int


class PracticeClub(_FileModel):
    key: Key
    name: Name
    short: Annotated[str, Field(min_length=1, max_length=40)] | None = None


class PracticeCorrection(_FileModel):
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    raw: RawSections


class PracticeStart(_FileModel):
    competition: Key
    state: StartState
    # Nummer des Durchgangs (nur bei Zeitplan).
    heat: PositiveInt | None = None
    raw: RawSections | None = None
    correction: PracticeCorrection | None = None
    abort_reason: Literal["dns", "dnf", "dsq"] | None = None
    note: Annotated[str, Field(min_length=1, max_length=500)] | None = None

    @model_validator(mode="after")
    def _check_state(self) -> Self:
        if self.state in ("final", "captured") and self.raw is None:
            raise ValueError(f"Ein Start im Zustand „{self.state}“ braucht Rohwerte (raw).")
        if self.state in ("registered", "called") and self.raw is not None:
            raise ValueError(f"Ein Start im Zustand „{self.state}“ hat keine Rohwerte.")
        if (self.state == "aborted") != (self.abort_reason is not None):
            raise ValueError("Genau ein abgebrochener Start braucht abort_reason.")
        if self.correction is not None and self.state != "final":
            raise ValueError("Korrigieren lässt sich nur ein abgeschlossener Start.")
        return self


class PracticePerson(_FileModel):
    name: Name
    club: Key | None = None
    class_code: Annotated[str, Field(alias="class", min_length=1)]
    display_mode: Literal["full", "short", "hidden"] = "full"
    show_club: bool = True
    starts: list[PracticeStart] = Field(default_factory=list)


class PracticeFile(TournamentTemplate):
    organizer: Name | None = None
    heats: list[PracticeHeats] = Field(default_factory=list)
    clubs: list[PracticeClub] = Field(default_factory=list)
    persons: Annotated[list[PracticePerson], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_practice_references(self) -> Self:
        clubs = {club.key for club in self.clubs}
        competitions = {item.key for item in self.competitions}
        for heats in self.heats:
            if heats.competition not in competitions:
                raise ValueError(f"Durchgänge für unbekannten Wettbewerb „{heats.competition}“.")
        for person in self.persons:
            if person.club is not None and person.club not in clubs:
                raise ValueError(f"{person.name}: Verein „{person.club}“ ist nicht angelegt.")
            for start in person.starts:
                if start.competition not in competitions:
                    raise ValueError(
                        f"{person.name}: Wettbewerb „{start.competition}“ ist nicht angelegt."
                    )
        return self


def load_practice(path: Path = PRACTICE_FILE) -> PracticeFile:
    return read_template_file(path, PracticeFile)


def sections_raw(raw: RawSections) -> dict[str, Any]:
    return {"sections": {section: {"series": series} for section, series in raw.items()}}


# --- Anlegen -------------------------------------------------------------------------


async def current_practice(session: AsyncSession) -> Tournament | None:
    return await session.scalar(select(Tournament).where(Tournament.is_practice))


def _heat_start(now: datetime, offset_minutes: int) -> datetime:
    floored = now.replace(second=0, microsecond=0)
    floored -= timedelta(minutes=floored.minute % 5)
    return floored + timedelta(minutes=offset_minutes)


async def create_practice(
    session: AsyncSession, events: EventHub, actor: Actor, index: Any
) -> Tournament:
    """Legt das Übungsturnier an (Status aktiv, heutiges Datum in der Ortszeit des Turniers)."""
    existing = await current_practice(session)
    if existing is not None:
        raise PracticeExistsError(existing)
    data = load_practice()
    timezone = ZoneInfo(TournamentSettings().timezone)
    if data.settings is not None and data.settings.timezone is not None:
        timezone = ZoneInfo(data.settings.timezone)
    today = datetime.now(timezone).date()
    create = TournamentCreate(
        name=data.name,
        organizer=data.organizer,
        date_from=today,
        template=data.template,
        settings=data.settings,
    )
    try:
        tournament, _, competitions = await build_from_template(
            session, events, actor, data, create, is_practice=True
        )
    except IntegrityError as exc:
        # Gleichzeitig angelegt: Der eindeutige Teilindex lässt nur eines zu.
        await session.rollback()
        existing = await current_practice(session)
        if existing is None:
            raise
        raise PracticeExistsError(existing) from exc

    tid = tournament.id
    owned: dict[str, list[str]] = {"person_ids": [], "club_ids": []}
    try:
        await _fill(session, events, actor, index, tid, data, competitions, owned)
    except Exception:
        # Halb angelegte Übung samt schon angelegter Personen und Vereine wieder entfernen.
        await session.rollback()
        await _store_owned(session, tid, owned)
        await remove_practice(session, events, actor, index, tid)
        raise
    return await service.get_tournament(session, tid)


async def _store_owned(
    session: AsyncSession, tournament_id: uuid.UUID, owned: dict[str, list[str]]
) -> None:
    tournament = await service.get_tournament(session, tournament_id)
    tournament.practice_data = {key: list(value) for key, value in owned.items()}
    await session.commit()


async def _fill(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    index: Any,
    tid: uuid.UUID,
    data: PracticeFile,
    competitions: dict[str, Competition],
    owned: dict[str, list[str]],
) -> None:
    from app.modules.ergebnisse import service as results
    from app.modules.starts import queue, schedule
    from app.modules.starts import service as starts
    from app.modules.starts.schemas import EntryCreate, HeatSeries, StartBooking
    from app.modules.teilnehmer import service as persons
    from app.modules.teilnehmer.models import Club
    from app.modules.teilnehmer.schemas import ClubCreate, PersonCreate

    # Vereine: vorhandene gleichen Namens werden mitbenutzt, aber nicht entfernt.
    club_ids: dict[str, uuid.UUID] = {}
    for club in data.clubs:
        found = await session.scalar(
            select(Club).where(func.lower(Club.name) == func.lower(club.name))
        )
        if found is not None:
            club_ids[club.key] = found.id
            continue
        created = await persons.create_club(
            session, index, events, ClubCreate(name=club.name, short=club.short)
        )
        club_ids[club.key] = created.id
        owned["club_ids"].append(str(created.id))

    classes = {item.code: item.id for item in await service._list(session, TournamentClass, tid)}
    width = max(2, math.ceil(math.log10(len(data.persons) + 1)))
    entries: list[uuid.UUID] = []
    for number, person in enumerate(data.persons, start=1):
        created_person = await persons.create_person(
            session,
            index,
            events,
            PersonCreate(
                name=person.name,
                member_no=f"{MEMBER_NO_PREFIX}{number:0{width}d}",
                club_id=club_ids[person.club] if person.club else None,
                display_mode=person.display_mode,
                show_club=person.show_club,
            ),
            force=True,
        )
        owned["person_ids"].append(str(created_person.id))
        entries.append(created_person.id)
    await _store_owned(session, tid, owned)

    # Aktiv wie am Wettkampftag; die Kennzeichnung „Übung“ bleibt davon unberührt.
    tournament = await service.get_tournament(session, tid)
    tournament.status = "active"
    await session.commit()
    events.publish(
        "tournament.status_changed", {"tournament_id": str(tid), "from": "draft", "to": "active"}
    )

    now = datetime.now(UTC)
    heats: dict[tuple[str, int], uuid.UUID] = {}
    for series in data.heats:
        competition = competitions[series.competition]
        assert competition.range_id is not None
        created_heats = await schedule.create_series(
            session,
            events,
            tid,
            competition.range_id,
            HeatSeries(
                competition_id=competition.id,
                starts_at=_heat_start(now, series.first_offset_minutes),
                count=series.count,
            ),
            actor,
        )
        for position, heat in enumerate(created_heats, start=1):
            heats[(series.competition, position)] = heat.id

    plan: list[tuple[PracticeStart, uuid.UUID]] = []
    for person, person_id in zip(data.persons, entries, strict=True):
        if person.class_code not in classes:
            raise service.InvalidError(
                f"{person.name}: Die Klasse „{person.class_code}“ gibt es im Turnier nicht."
            )
        entry = await starts.create_entry(
            session,
            events,
            actor,
            tid,
            EntryCreate(person_id=person_id, class_id=classes[person.class_code]),
        )
        for item in person.starts:
            heat_id = heats[(item.competition, item.heat)] if item.heat is not None else None
            booked = await starts.book_starts(
                session,
                events,
                actor,
                tid,
                entry.id,
                StartBooking(competition_id=competitions[item.competition].id, heat_id=heat_id),
            )
            plan.append((item, booked[0].id))

    # Erst alles, was die Bahn wieder freigibt, dann die Starts, die auf der Bahn stehen bleiben.
    ordered = [step for step in plan if step[0].state not in ON_LANE_STATES] + [
        step for step in plan if step[0].state in ON_LANE_STATES
    ]
    for item, start_id in ordered:
        if item.state == "registered":
            continue
        if item.state == "aborted" and item.raw is None:
            await results.abort(
                session, events, actor, tid, start_id, item.abort_reason, item.note, None
            )
            continue
        await queue.call(session, events, actor, tid, start_id, None)
        if item.state == "called":
            continue
        assert item.raw is not None
        state = await results.set_raw(
            session, events, actor, tid, start_id, sections_raw(item.raw), 0, None
        )
        if item.state == "final":
            state = await results.finalize(session, events, actor, tid, start_id, state.seq, None)
            if item.correction is not None:
                await results.correct(
                    session,
                    events,
                    actor,
                    tid,
                    start_id,
                    sections_raw(item.correction.raw),
                    item.correction.reason,
                    state.seq,
                    None,
                )
        elif item.state == "aborted":
            await results.abort(
                session, events, actor, tid, start_id, item.abort_reason, item.note, None
            )


# --- Entfernen -----------------------------------------------------------------------


async def remove_practice(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    index: Any,
    tournament_id: uuid.UUID,
) -> None:
    """Entfernt das Übungsturnier samt Beispieldaten in einer Transaktion."""
    from app.modules.ergebnisse.models import ResultCurrent, ResultEvent
    from app.modules.starts.models import Entry, Start
    from app.modules.teilnehmer.models import Club, Person

    tournament = await service.get_tournament(session, tournament_id)
    if not tournament.is_practice:
        raise service.ConflictError("Das Turnier ist kein Übungsturnier.")
    owned = tournament.practice_data or {}
    entry_ids = select(Entry.id).where(Entry.tournament_id == tournament_id)
    start_ids = select(Start.id).where(Start.entry_id.in_(entry_ids))
    await session.execute(delete(ResultEvent).where(ResultEvent.start_id.in_(start_ids)))
    await session.execute(delete(ResultCurrent).where(ResultCurrent.start_id.in_(start_ids)))
    await session.execute(delete(Start).where(Start.entry_id.in_(entry_ids)))
    await session.execute(delete(Entry).where(Entry.tournament_id == tournament_id))
    await session.execute(
        delete(AuditLog).where(AuditLog.details["tournament_id"].astext == str(tournament_id))
    )
    # Stände (samt Durchgängen), Klassen und Wettbewerbe löscht die Datenbank mit.
    await session.execute(delete(Tournament).where(Tournament.id == tournament_id))

    person_ids = [uuid.UUID(value) for value in owned.get("person_ids", [])]
    # Wer inzwischen auch in einem anderen Turnier gemeldet ist, bleibt.
    still_entered = set(
        await session.scalars(select(Entry.person_id).where(Entry.person_id.in_(person_ids)))
    )
    removed_persons = [person_id for person_id in person_ids if person_id not in still_entered]
    if removed_persons:
        await session.execute(delete(Person).where(Person.id.in_(removed_persons)))
    club_ids = [uuid.UUID(value) for value in owned.get("club_ids", [])]
    still_used = set(
        await session.scalars(select(Person.club_id).where(Person.club_id.in_(club_ids)))
    )
    removed_clubs = [club_id for club_id in club_ids if club_id not in still_used]
    if removed_clubs:
        await session.execute(delete(Club).where(Club.id.in_(removed_clubs)))
    record_audit(
        session,
        actor,
        "tournament.practice_removed",
        "tournament",
        tournament_id,
        {
            "persons_removed": len(removed_persons),
            "persons_kept": len(person_ids) - len(removed_persons),
            "clubs_removed": len(removed_clubs),
        },
    )
    await session.commit()
    session.expunge_all()

    for person_id in removed_persons:
        index.remove_person(person_id)
        events.publish("person.deleted", {"person_id": str(person_id)})
    for club_id in removed_clubs:
        index.remove_club(club_id)
        events.publish("club.deleted", {"club_id": str(club_id)})
    events.publish("tournament.deleted", {"tournament_id": str(tournament_id)})
