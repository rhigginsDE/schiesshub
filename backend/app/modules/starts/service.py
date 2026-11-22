"""Anmeldungen und Starts: Anmelden, Ändern, Löschen, Suchen, Starts buchen und stornieren.

Nach jeder Änderung geht ein Ereignis an die Clients (`entry.*`, `start.*`, Nutzlast nur IDs).
Wichtige Vorgänge landen im Audit-Protokoll, in derselben Transaktion wie die Änderung.
In einem abgeschlossenen Turnier ist nichts davon möglich.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence

from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InputError
from app.core.events import EventHub
from app.core.security import Actor
from app.modules.auth.audit import record_audit
from app.modules.starts import hooks, schedule
from app.modules.starts.common import (
    ConflictError,
    event_ids,
    get_entry,
    get_range,
    get_start,
    get_tournament,
    renumber_queue,
    writable_tournament,
)
from app.modules.starts.deletion import turnier_deletion_check
from app.modules.starts.lifecycle import publish_status, transition
from app.modules.starts.models import Entry, Start
from app.modules.starts.rules import (
    AbortReason,
    RuleError,
    check_start_limit,
    first_start_number,
    has_result,
    next_free_number,
    start_fee,
)
from app.modules.starts.schemas import (
    EntryCreate,
    EntryOut,
    EntryPersonOut,
    EntryUpdate,
    StartBooking,
    StartOut,
)
from app.modules.teilnehmer.index import PersonIndex
from app.modules.teilnehmer.models import Club, Person
from app.modules.teilnehmer.names import display_name
from app.modules.teilnehmer.service import register_person_deletion_check
from app.modules.turnier.hooks import register_deletion_check
from app.modules.turnier.models import Competition, Tournament, TournamentClass

EVENT_ENTRY_CREATED = "entry.created"
EVENT_ENTRY_UPDATED = "entry.updated"
EVENT_ENTRY_DELETED = "entry.deleted"
EVENT_START_BOOKED = "start.booked"
EVENT_START_CANCELLED = "start.cancelled"


# --- Ausgabe -----------------------------------------------------------------


async def entry_outs(session: AsyncSession, entries: Sequence[Entry]) -> list[EntryOut]:
    """Anmeldungen mit Person und Starts, in der Reihenfolge von `entries`."""
    if not entries:
        return []
    person_rows = await session.execute(
        select(Person, Club.name)
        .outerjoin(Club, Club.id == Person.club_id)
        .where(Person.id.in_({entry.person_id for entry in entries}))
    )
    persons = {person.id: (person, club) for person, club in person_rows}
    starts: dict[uuid.UUID, list[Start]] = defaultdict(list)
    for start in await session.scalars(
        select(Start)
        .where(Start.entry_id.in_([entry.id for entry in entries]))
        .order_by(Start.created_at, Start.competition_id, Start.attempt)
    ):
        starts[start.entry_id].append(start)

    result = []
    for entry in entries:
        person, club = persons[entry.person_id]
        own = starts[entry.id]
        result.append(
            EntryOut(
                id=entry.id,
                tournament_id=entry.tournament_id,
                start_number=entry.start_number,
                class_id=entry.class_id,
                person=EntryPersonOut(
                    id=person.id,
                    name=person.name_enc,
                    display_name=display_name(person.name_enc, person.display_mode),
                    club=club,
                ),
                starts=[StartOut.model_validate(start) for start in own],
                fee_total_cents=sum(start.fee_cents for start in own),
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
        )
    return result


async def entry_out(session: AsyncSession, entry: Entry) -> EntryOut:
    await session.refresh(entry)
    return (await entry_outs(session, [entry]))[0]


# --- Anmeldung ---------------------------------------------------------------


async def list_entries(
    session: AsyncSession,
    index: PersonIndex,
    tournament_id: uuid.UUID,
    query: str | None,
    class_id: uuid.UUID | None,
) -> list[EntryOut]:
    """Anmeldungen nach Startnummer, oder Treffer für `query`.

    Gesucht wird nach Startnummer (genau) und über den Suchindex der Teilnehmer (Name,
    Mitgliedsnummer, Verein). Treffer der Startnummer stehen vorn.
    """
    await get_tournament(session, tournament_id)
    statement = select(Entry).where(Entry.tournament_id == tournament_id)
    if class_id is not None:
        statement = statement.where(Entry.class_id == class_id)
    entries = list(await session.scalars(statement.order_by(Entry.start_number)))
    text = (query or "").strip()
    if text:
        by_number = [e for e in entries if text.isdigit() and e.start_number == int(text)]
        rank = {person_id: i for i, person_id in enumerate(index.search(text))}
        by_name = sorted(
            (e for e in entries if e.person_id in rank and e not in by_number),
            key=lambda e: rank[e.person_id],
        )
        entries = by_number + by_name
    return await entry_outs(session, entries)


async def _class_of_tournament(
    session: AsyncSession, tournament_id: uuid.UUID, class_id: uuid.UUID
) -> TournamentClass:
    item = await session.get(TournamentClass, class_id)
    if item is None or item.tournament_id != tournament_id:
        raise InputError.single("class_id", "Die Klasse gehört nicht zu diesem Turnier.")
    return item


async def _check_number_free(
    session: AsyncSession, tournament_id: uuid.UUID, number: int, own_id: uuid.UUID | None
) -> None:
    holder = await session.scalar(
        select(Entry.id).where(Entry.tournament_id == tournament_id, Entry.start_number == number)
    )
    if holder is not None and holder != own_id:
        raise ConflictError(
            f"Die Startnummer {number} ist in diesem Turnier schon vergeben.", field="start_number"
        )


async def create_entry(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    data: EntryCreate,
) -> EntryOut:
    # Gesperrt, damit zwei gleichzeitige Anmeldungen nicht dieselbe Nummer ziehen.
    tournament = await writable_tournament(session, tournament_id, lock=True)
    if await session.get(Person, data.person_id) is None:
        raise InputError.single("person_id", "Diese Person gibt es nicht.")
    await _class_of_tournament(session, tournament_id, data.class_id)
    existing = await session.scalar(
        select(Entry.start_number).where(
            Entry.tournament_id == tournament_id, Entry.person_id == data.person_id
        )
    )
    if existing is not None:
        raise ConflictError(
            f"Diese Person ist in diesem Turnier schon angemeldet (Startnummer {existing}).",
            field="person_id",
        )
    if data.start_number is not None:
        await _check_number_free(session, tournament_id, data.start_number, None)
        number = data.start_number
    else:
        used = await session.scalars(
            select(Entry.start_number).where(Entry.tournament_id == tournament_id)
        )
        number = next_free_number(used, first_start_number(tournament.settings))

    entry = Entry(
        tournament_id=tournament_id,
        person_id=data.person_id,
        class_id=data.class_id,
        start_number=number,
    )
    session.add(entry)
    await session.flush()
    record_audit(
        session,
        actor,
        "entry.created",
        "entry",
        entry.id,
        {
            "tournament_id": str(tournament_id),
            "person_id": str(data.person_id),
            "class_id": str(data.class_id),
            "start_number": number,
        },
    )
    await session.commit()
    events.publish(
        EVENT_ENTRY_CREATED,
        event_ids(tournament_id=tournament_id, entry_id=entry.id, person_id=entry.person_id),
    )
    return await entry_out(session, entry)


async def get_entry_out(
    session: AsyncSession, tournament_id: uuid.UUID, entry_id: uuid.UUID
) -> EntryOut:
    return await entry_out(session, await get_entry(session, tournament_id, entry_id))


async def update_entry(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    entry_id: uuid.UUID,
    data: EntryUpdate,
) -> EntryOut:
    await writable_tournament(session, tournament_id, lock=True)
    entry = await get_entry(session, tournament_id, entry_id)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None:
            raise InputError.single(key, f"Das Feld „{key}“ darf nicht leer sein.")
    if "class_id" in changes and changes["class_id"] != entry.class_id:
        new_class = await _class_of_tournament(session, tournament_id, changes["class_id"])
        blocked = await session.scalars(
            select(Competition.name)
            .join(Start, Start.competition_id == Competition.id)
            .where(
                Start.entry_id == entry.id,
                func.cardinality(Competition.class_ids) > 0,
                func.array_position(Competition.class_ids, new_class.id).is_(None),
            )
            .distinct()
            .order_by(Competition.name)
        )
        names = list(blocked)
        if names:
            listed = ", ".join(f"„{name}“" for name in names)
            raise ConflictError(
                f"Die Klasse „{new_class.name}“ ist in {listed} nicht zugelassen, dort hat die "
                "Anmeldung aber Starts. Bitte die Starts erst stornieren.",
                field="class_id",
            )
    if "start_number" in changes:
        await _check_number_free(session, tournament_id, changes["start_number"], entry.id)

    before = {key: getattr(entry, key) for key in changes}
    for key, value in changes.items():
        setattr(entry, key, value)
    record_audit(
        session,
        actor,
        "entry.updated",
        "entry",
        entry.id,
        {
            "tournament_id": str(tournament_id),
            "before": {key: _plain(value) for key, value in before.items()},
            "after": {key: _plain(value) for key, value in changes.items()},
        },
    )
    await session.commit()
    events.publish(EVENT_ENTRY_UPDATED, event_ids(tournament_id=tournament_id, entry_id=entry.id))
    return await entry_out(session, entry)


async def delete_entry(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    entry_id: uuid.UUID,
) -> None:
    await writable_tournament(session, tournament_id, lock=True)
    entry = await get_entry(session, tournament_id, entry_id)
    starts = list(await session.scalars(select(Start).where(Start.entry_id == entry.id)))
    if any(has_result(start.status, start.abort_reason) for start in starts):
        raise ConflictError(
            "Die Anmeldung hat Starts, die schon geschossen wurden oder gerade aufgerufen sind. "
            "Sie lässt sich deshalb nicht löschen."
        )
    if await hooks.starts_with_results(session, [start.id for start in starts]):
        raise ConflictError(
            "Zu Starts dieser Anmeldung gibt es Einträge im Ergebnisprotokoll (zum Beispiel "
            "„nicht angetreten“). Die Anmeldung lässt sich deshalb nicht löschen."
        )
    ranges = await _queue_ranges(session, starts)
    record_audit(
        session,
        actor,
        "entry.deleted",
        "entry",
        entry.id,
        {
            "tournament_id": str(tournament_id),
            "person_id": str(entry.person_id),
            "start_number": entry.start_number,
            "start_ids": [str(start.id) for start in starts],
        },
    )
    # Die Starts löscht die Datenbank mit (ON DELETE CASCADE).
    await session.delete(entry)
    await session.flush()
    for range_id in ranges:
        await renumber_queue(session, range_id)
    await session.commit()
    events.publish(
        EVENT_ENTRY_DELETED,
        event_ids(tournament_id=tournament_id, entry_id=entry_id, person_id=entry.person_id),
    )


def _plain(value: object) -> object:
    return str(value) if isinstance(value, uuid.UUID) else value


async def _queue_ranges(session: AsyncSession, starts: Sequence[Start]) -> set[uuid.UUID]:
    """Stände, deren Reihenfolge die Starts berühren."""
    if not starts:
        return set()
    rows = await session.scalars(
        select(Competition.range_id).where(
            Competition.id.in_({start.competition_id for start in starts}),
            Competition.planning == "queue",
            Competition.range_id.is_not(None),
        )
    )
    return {range_id for range_id in rows if range_id is not None}


# --- Starts buchen und stornieren --------------------------------------------


async def book_starts(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    entry_id: uuid.UUID,
    data: StartBooking,
) -> list[Start]:
    """Bucht `count` Starts. Der Betrag wird dabei am Start festgeschrieben."""
    await writable_tournament(session, tournament_id, lock=True)
    entry = await get_entry(session, tournament_id, entry_id)
    competition = await session.get(Competition, data.competition_id)
    if competition is None or competition.tournament_id != tournament_id:
        raise InputError.single("competition_id", "Der Wettbewerb gehört nicht zu diesem Turnier.")
    if competition.class_ids and entry.class_id not in competition.class_ids:
        class_name = await session.scalar(
            select(TournamentClass.name).where(TournamentClass.id == entry.class_id)
        )
        raise ConflictError(
            f"Die Klasse „{class_name}“ ist im Wettbewerb „{competition.name}“ nicht zugelassen.",
            field="competition_id",
        )
    if data.heat_id is None and data.lane is not None:
        raise InputError.single(
            "lane",
            "Eine Bahn lässt sich beim Buchen nur zusammen mit einem Durchgang vergeben; bei "
            "der Reihenfolge wird sie erst beim Aufrufen vergeben.",
        )
    if data.heat_id is not None and data.count != 1:
        raise InputError.single(
            "count", "Mit Durchgang lässt sich nur ein Start auf einmal buchen."
        )

    booked = (
        await session.scalar(
            select(func.count())
            .select_from(Start)
            .where(Start.entry_id == entry.id, Start.competition_id == competition.id)
        )
        or 0
    )
    try:
        check_start_limit(competition.multi_start, competition.max_starts, booked, data.count)
    except RuleError as exc:
        raise ConflictError(str(exc), field="count") from exc

    in_queue = competition.planning == "queue" and competition.range_id is not None
    # Neue Starts kommen ans Ende der Reihenfolge ihres Stands.
    position = len(await renumber_queue(session, competition.range_id)) if in_queue else 0
    starts = [
        Start(
            entry_id=entry.id,
            competition_id=competition.id,
            attempt=booked + offset,
            fee_cents=start_fee(
                booked + offset, competition.fee_first_cents, competition.fee_repeat_cents
            ),
            status="registered",
            queue_position=position + offset if in_queue else None,
        )
        for offset in range(1, data.count + 1)
    ]
    session.add_all(starts)
    await session.flush()
    if data.heat_id is not None:
        await schedule.place(session, starts[0], entry, competition, data.heat_id, data.lane)

    record_audit(
        session,
        actor,
        "start.booked",
        "entry",
        entry.id,
        {
            "tournament_id": str(tournament_id),
            "entry_id": str(entry.id),
            "competition_id": str(competition.id),
            "competition_code": competition.catalog_code,
            "competition_name": competition.name,
            # Mehrere Starts einer Buchung gehören zur selben Anmeldung, also einer Startnummer.
            "start_number": entry.start_number,
            "attempts": [start.attempt for start in starts],
            "start_ids": [str(start.id) for start in starts],
            "fee_cents": [start.fee_cents for start in starts],
        },
    )
    await session.commit()
    events.publish(
        EVENT_START_BOOKED,
        {
            **event_ids(
                tournament_id=tournament_id,
                entry_id=entry.id,
                competition_id=competition.id,
                range_id=competition.range_id,
            ),
            "start_ids": [str(start.id) for start in starts],
        },
    )
    for start in starts:
        await session.refresh(start)
    return starts


async def cancel_start(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
) -> None:
    """Storno: nur im Status `registered`. Danach rücken die übrigen Versuche nach.

    Die Beträge bleiben an ihrer Position: Wer den ersten von zwei Starts storniert, zahlt für
    den verbleibenden weiterhin den Betrag des ersten Starts.
    """
    await writable_tournament(session, tournament_id, lock=True)
    context = await get_start(session, tournament_id, start_id)
    start, competition = context.start, context.competition
    if start.status != "registered":
        raise ConflictError(
            "Stornieren geht nur, solange der Start noch nicht aufgerufen wurde. Danach lässt "
            "er sich nur noch abbrechen (dns, dnf, dsq)."
        )
    if await hooks.starts_with_results(session, [start.id]):
        raise ConflictError(
            "Zu diesem Start gibt es schon Einträge im Ergebnisprotokoll. Er lässt sich "
            "deshalb nicht stornieren, nur noch abbrechen (dns, dnf, dsq)."
        )
    siblings = list(
        await session.scalars(
            select(Start)
            .where(Start.entry_id == start.entry_id, Start.competition_id == competition.id)
            .order_by(Start.attempt)
        )
    )
    fees = [sibling.fee_cents for sibling in siblings]
    remaining = [sibling for sibling in siblings if sibling.id != start.id]
    record_audit(
        session,
        actor,
        "start.cancelled",
        "start",
        start.id,
        context.audit_details(fee_cents=start.fee_cents),
    )
    await session.delete(start)
    for attempt, (sibling, fee) in enumerate(
        zip(remaining, fees[: len(remaining)], strict=True), start=1
    ):
        sibling.attempt = attempt
        sibling.fee_cents = fee
    await session.flush()
    if competition.planning == "queue" and competition.range_id is not None:
        await renumber_queue(session, competition.range_id)
    await session.commit()
    events.publish(
        EVENT_START_CANCELLED,
        event_ids(
            tournament_id=tournament_id,
            entry_id=start.entry_id,
            start_id=start_id,
            competition_id=competition.id,
            range_id=competition.range_id,
        ),
    )


async def abort_start(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    abort_reason: AbortReason,
    note: str | None = None,
) -> Start:
    """Bricht einen Start ab, wahlweise mit Bemerkung (`note`).

    Ist ein Abbruch-Handler angemeldet (Modul `ergebnisse`), übernimmt er den ganzen Vorgang;
    der Abbruch steht dann auch im Ergebnisprotokoll, die Bemerkung als Grund am Ereignis
    `aborted`. Sonst wechselt nur der Status. In beiden Fällen steht die Bemerkung als
    `reason` im Audit-Eintrag `start.aborted`.
    """
    context = await get_start(session, tournament_id, start_id)
    handler = hooks.abort_handler()
    if handler is not None:
        await handler(session, events, actor, tournament_id, start_id, abort_reason, note)
        start = await session.get(Start, start_id, populate_existing=True)
        assert start is not None
        return start
    if context.competition.range_id is not None:
        # Wie alle Vorgänge an den Bahnen eines Stands nacheinander.
        await get_range(session, tournament_id, context.competition.range_id, lock=True)
    change = await transition(
        session, context.start, "aborted", actor, abort_reason=abort_reason, reason=note
    )
    await session.commit()
    publish_status(events, change)
    await session.refresh(context.start)
    return context.start


# --- Löschschutz für Personen ------------------------------------------------


async def person_deletion_check(session: AsyncSession, person_id: uuid.UUID) -> str | None:
    names = list(
        await session.scalars(
            select(Tournament.name)
            .join(Entry, Entry.tournament_id == Tournament.id)
            .where(Entry.person_id == person_id)
            .order_by(Tournament.date_from, Tournament.name)
        )
    )
    if not names:
        return None
    listed = ", ".join(f"„{name}“" for name in names)
    if len(names) == 1:
        return f"Die Person ist im Turnier {listed} angemeldet."
    return f"Die Person ist in den Turnieren {listed} angemeldet."


async def on_startup(app: FastAPI) -> None:
    register_person_deletion_check(person_deletion_check)
    register_deletion_check(turnier_deletion_check)
