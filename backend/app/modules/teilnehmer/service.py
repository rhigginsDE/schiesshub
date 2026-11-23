"""Vereine und Personen: Anlegen, Ändern, Löschen, Suche, Import und Export.

Regeln für personenbezogene Daten:
- Namen und Mitgliedsnummern erscheinen nie in Logs oder Ereignissen; Ereignisse tragen nur IDs.
- Der Suchindex (`index.PersonIndex`) wird erst nach dem erfolgreichen Commit nachgeführt.
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import ScalarSelect, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import setup_field_cipher
from app.core.events import EventHub
from app.modules.teilnehmer import csvio
from app.modules.teilnehmer.index import PersonIndex
from app.modules.teilnehmer.models import Club, Person
from app.modules.teilnehmer.names import clean_text, display_name, fold
from app.modules.teilnehmer.schemas import (
    ClubCreate,
    ClubOut,
    ClubUpdate,
    ImportReportOut,
    ImportRowOut,
    PersonCreate,
    PersonOut,
    PersonUpdate,
)

logger = logging.getLogger("schiesshub.teilnehmer")

EVENT_CLUB_CREATED = "club.created"
EVENT_CLUB_UPDATED = "club.updated"
EVENT_CLUB_DELETED = "club.deleted"
EVENT_CLUB_MERGED = "club.merged"
EVENT_PERSON_CREATED = "person.created"
EVENT_PERSON_UPDATED = "person.updated"
EVENT_PERSON_DELETED = "person.deleted"
EVENT_PERSON_IMPORTED = "person.imported"


class NotFoundError(Exception):
    """Verein oder Person gibt es nicht. Die Meldung ist für Anwender gedacht."""


class InvalidReferenceError(Exception):
    """Ein Verweis in den Eingabedaten zeigt ins Leere (z. B. unbekannter Verein)."""


class ConflictError(Exception):
    """Die Änderung widerspricht dem Datenbestand (z. B. Vereinsname schon vergeben)."""


class DuplicateError(Exception):
    """Beim Anlegen gibt es schon Personen mit gleichem Namen im selben Verein."""

    def __init__(self, message: str, candidates: list[PersonOut]) -> None:
        super().__init__(message)
        self.candidates = candidates


class ClubCreationForbiddenError(Exception):
    """Der Verein aus `club_name` fehlt, und dem Anfragenden fehlt `club.edit` zum Anlegen."""


# Fragt, ob der Anfragende einen neuen Verein anlegen darf (`club.edit`). Wird nur aufgerufen,
# wenn der Verein aus `club_name` wirklich fehlt.
ClubCreationCheck = Callable[[], Awaitable[bool]]


class DeletionBlockedError(Exception):
    """Ein anderes Modul verhindert das Löschen einer Person."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__(" ".join(reasons))
        self.reasons = reasons


# --- Löschprüfung für andere Module ------------------------------------------

# Ein Prüfer bekommt Sitzung und Personen-ID und liefert einen deutschen Satz, warum die Person
# nicht gelöscht werden darf, oder None. Beispiel (Modul `starts`): „Die Person ist in einem
# laufenden Turnier angemeldet.“
PersonDeletionCheck = Callable[[AsyncSession, UUID], Awaitable[str | None]]

_person_deletion_checks: list[PersonDeletionCheck] = []


def register_person_deletion_check(check: PersonDeletionCheck) -> None:
    """Meldet einen Prüfer an, der vor dem endgültigen Löschen einer Person gefragt wird."""
    if check not in _person_deletion_checks:
        _person_deletion_checks.append(check)


def unregister_person_deletion_check(check: PersonDeletionCheck) -> None:
    if check in _person_deletion_checks:
        _person_deletion_checks.remove(check)


async def can_delete_person(session: AsyncSession, person_id: UUID) -> list[str]:
    """Fragt alle angemeldeten Prüfer. Leere Liste: Die Person darf gelöscht werden."""
    reasons: list[str] = []
    for check in _person_deletion_checks:
        reason = await check(session, person_id)
        if reason:
            reasons.append(reason)
    return reasons


# --- Start -------------------------------------------------------------------


async def rebuild_index(session: AsyncSession, index: PersonIndex) -> None:
    clubs = (await session.execute(select(Club.id, Club.name))).all()
    persons = await session.execute(
        select(Person.id, Person.name_enc, Person.member_no_enc, Person.club_id)
    )
    index.load(persons, clubs)


async def on_startup(app: FastAPI) -> None:
    """Schlüssel laden (beim ersten Start erzeugen) und den Suchindex füllen."""
    keys_dir = app.state.settings.data_dir / "keys"
    index = PersonIndex()
    async with app.state.session_factory() as session:
        person_count = await session.scalar(select(func.count()).select_from(Person)) or 0
        # Gibt es schon verschlüsselte Daten, darf kein neuer Schlüssel entstehen.
        cipher = setup_field_cipher(keys_dir, create=person_count == 0)
        await rebuild_index(session, index)
    app.state.person_index = index
    logger.info(
        "Feldverschlüsselung bereit (aktiver Schlüssel %s), Suchindex mit %d Personen geladen.",
        cipher.active_key_id,
        len(index),
    )


# --- Vereine -----------------------------------------------------------------


def _club_count_query() -> ScalarSelect[int]:
    return (
        select(func.count()).select_from(Person).where(Person.club_id == Club.id).scalar_subquery()
    )


def _club_out(club: Club, person_count: int) -> ClubOut:
    return ClubOut(
        id=club.id,
        name=club.name,
        short=club.short,
        person_count=person_count,
        created_at=club.created_at,
        updated_at=club.updated_at,
    )


async def list_clubs(session: AsyncSession, query: str | None = None) -> list[ClubOut]:
    """Vereine nach Name; mit `query` nur Treffer in Name oder Kürzel.

    Verglichen wird wie bei Personen ohne Groß-/Kleinschreibung und Umlaut-Schreibweise.
    Treffer am Anfang von Name oder Kürzel stehen vorn.
    """
    rows = await session.execute(select(Club, _club_count_query()).order_by(func.lower(Club.name)))
    clubs = [(club, count) for club, count in rows]
    needle = fold(query or "")
    if needle:
        ranked = []
        for position, (club, count) in enumerate(clubs):
            fields = [fold(club.name), fold(club.short or "")]
            if any(field.startswith(needle) for field in fields):
                ranked.append((0, position, club, count))
            elif any(needle in field for field in fields):
                ranked.append((1, position, club, count))
        clubs = [(club, count) for _, _, club, count in sorted(ranked, key=lambda r: r[:2])]
    return [_club_out(club, count) for club, count in clubs]


async def get_club(session: AsyncSession, club_id: UUID) -> ClubOut:
    row = (
        await session.execute(
            select(Club, _club_count_query())
            .where(Club.id == club_id)
            .execution_options(populate_existing=True)
        )
    ).first()
    if row is None:
        raise NotFoundError("Diesen Verein gibt es nicht.")
    return _club_out(*row)


async def _clubs_like(session: AsyncSession, name: str) -> list[Club]:
    """Alle Vereine mit gleicher Vergleichsform (`names.fold`), nach Name sortiert.

    So vergleichen Vereinsanlage, Umbenennen, `club_name` an der Person und der CSV-Import:
    ohne Groß-/Kleinschreibung, Akzente und Umlaut-Schreibweise („Schutzengilde“ und
    „Schuetzengilde“ sind derselbe Verein wie „Schützengilde“).
    """
    folded = fold(name)
    clubs = (await session.scalars(select(Club).order_by(func.lower(Club.name), Club.id))).all()
    return [club for club in clubs if fold(club.name) == folded]


def _club_name_taken(name: str) -> ConflictError:
    return ConflictError(f"Einen Verein mit dem Namen „{name}“ gibt es schon.")


async def _commit_club(session: AsyncSession, name: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _club_name_taken(name) from exc


async def create_club(
    session: AsyncSession, index: PersonIndex, events: EventHub, data: ClubCreate
) -> ClubOut:
    name = clean_text(data.name)
    if await _clubs_like(session, name):
        raise _club_name_taken(name)
    club = Club(name=name, short=data.short)
    session.add(club)
    await _commit_club(session, name)
    index.put_club(club.id, club.name)
    events.publish(EVENT_CLUB_CREATED, {"club_id": str(club.id)})
    return await get_club(session, club.id)


async def update_club(
    session: AsyncSession, index: PersonIndex, events: EventHub, club_id: UUID, data: ClubUpdate
) -> ClubOut:
    club = await session.get(Club, club_id)
    if club is None:
        raise NotFoundError("Diesen Verein gibt es nicht.")
    if "name" in data.model_fields_set and data.name is not None:
        name = clean_text(data.name)
        if any(other.id != club.id for other in await _clubs_like(session, name)):
            raise _club_name_taken(name)
        club.name = name
    if "short" in data.model_fields_set:
        club.short = data.short
    await _commit_club(session, club.name)
    index.put_club(club.id, club.name)
    events.publish(EVENT_CLUB_UPDATED, {"club_id": str(club.id)})
    return await get_club(session, club.id)


async def delete_club(
    session: AsyncSession, index: PersonIndex, events: EventHub, club_id: UUID
) -> None:
    club = await get_club(session, club_id)
    if club.person_count:
        raise ConflictError(
            f"Der Verein hat noch {club.person_count} Person(en). Bitte die Personen erst einem "
            "anderen Verein zuordnen oder den Verein zusammenführen."
        )
    await session.execute(delete(Club).where(Club.id == club_id))
    await session.commit()
    index.remove_club(club_id)
    events.publish(EVENT_CLUB_DELETED, {"club_id": str(club_id)})


async def merge_clubs(
    session: AsyncSession, index: PersonIndex, events: EventHub, club_id: UUID, into_id: UUID
) -> ClubOut:
    """Hängt alle Personen von `club_id` an `into_id` und löscht `club_id`."""
    if club_id == into_id:
        raise ConflictError("Ein Verein kann nicht mit sich selbst zusammengeführt werden.")
    if await session.get(Club, club_id) is None:
        raise NotFoundError("Den Verein, der aufgelöst werden soll, gibt es nicht.")
    if await session.get(Club, into_id) is None:
        raise InvalidReferenceError("Den Zielverein der Zusammenführung gibt es nicht.")
    moved = (
        await session.scalars(
            update(Person)
            .where(Person.club_id == club_id)
            .values(club_id=into_id, updated_at=func.now())
            .returning(Person.id)
        )
    ).all()
    await session.execute(delete(Club).where(Club.id == club_id))
    await session.commit()
    index.move_club_members(club_id, into_id)
    index.remove_club(club_id)
    events.publish(
        EVENT_CLUB_MERGED,
        {"club_id": str(club_id), "into_id": str(into_id), "person_ids": [str(i) for i in moved]},
    )
    logger.info(
        "Verein %s in %s zusammengeführt, %d Person(en) umgehängt.", club_id, into_id, len(moved)
    )
    return await get_club(session, into_id)


# --- Personen ----------------------------------------------------------------


def _person_out(person: Person, club_name: str | None) -> PersonOut:
    return PersonOut(
        id=person.id,
        name=person.name_enc,
        member_no=person.member_no_enc,
        club_id=person.club_id,
        club_name=club_name,
        display_mode=person.display_mode,  # type: ignore[arg-type]  # per CHECK abgesichert
        show_club=person.show_club,
        display_name=display_name(person.name_enc, person.display_mode),  # type: ignore[arg-type]
        display_club=club_name if person.show_club else None,
        created_at=person.created_at,
        updated_at=person.updated_at,
    )


async def _persons_by_ids(session: AsyncSession, ids: Sequence[UUID]) -> list[PersonOut]:
    """Lädt Personen in genau der Reihenfolge von `ids`."""
    if not ids:
        return []
    rows = await session.execute(
        select(Person, Club.name)
        .outerjoin(Club, Club.id == Person.club_id)
        .where(Person.id.in_(ids))
        .execution_options(populate_existing=True)
    )
    by_id = {person.id: _person_out(person, club_name) for person, club_name in rows}
    return [by_id[person_id] for person_id in ids if person_id in by_id]


async def get_person(session: AsyncSession, person_id: UUID) -> PersonOut:
    found = await _persons_by_ids(session, [person_id])
    if not found:
        raise NotFoundError("Diese Person gibt es nicht.")
    return found[0]


async def list_persons(
    session: AsyncSession, index: PersonIndex, query: str | None, limit: int, offset: int
) -> tuple[list[PersonOut], int]:
    """Personen nach Name sortiert oder als Suchtreffer; dazu die Gesamtzahl der Treffer."""
    ids = index.search(query) if query and query.strip() else index.all_sorted()
    return await _persons_by_ids(session, ids[offset : offset + limit]), len(ids)


async def _require_club(session: AsyncSession, club_id: UUID | None) -> None:
    if club_id is not None and await session.get(Club, club_id) is None:
        raise InvalidReferenceError("Den angegebenen Verein gibt es nicht.")


async def _find_club_like(session: AsyncSession, name: str) -> Club | None:
    """Verein mit gleicher Vergleichsform (`names.fold`) wie in der Vereinssuche.

    Passen mehrere (etwa „Köhler SV“ und „Koehler SV“), gewinnt die gleiche Schreibweise ohne
    Groß-/Kleinschreibung, sonst der erste nach Name.
    """
    return _pick_club(await _clubs_like(session, name), name)


def _pick_club(found: Sequence[Club], name: str) -> Club | None:
    """Aus Vereinen gleicher Vergleichsform: die gleiche Schreibweise, sonst den ersten."""
    if not found:
        return None
    same_spelling = name.casefold()
    return next((club for club in found if club.name.casefold() == same_spelling), found[0])


async def _club_for_name(
    session: AsyncSession, club_name: str, may_create_club: ClubCreationCheck | None
) -> tuple[Club, bool]:
    """Sucht den Verein zu `club_name` oder legt ihn in der laufenden Transaktion an.

    Liefert den Verein und ob er neu ist. Bestätigt wird erst zusammen mit der Person; ohne
    `may_create_club` (Aufruf aus dem Server selbst) ist das Anlegen erlaubt.
    """
    name = clean_text(club_name)
    club = await _find_club_like(session, name)
    if club is not None:
        return club, False
    if may_create_club is not None and not await may_create_club():
        raise ClubCreationForbiddenError(
            f"Den Verein „{name}“ gibt es noch nicht. Neue Vereine anlegen darf nur, wer die "
            "Berechtigung „club.edit“ hat. Bitte einen vorhandenen Verein wählen."
        )
    club = Club(name=name)
    session.add(club)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Gleichzeitig hat jemand denselben Verein angelegt.
        raise _club_name_taken(name) from exc
    return club, True


async def _commit_person(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        if "uq_club_name_ci" in str(exc.orig):
            raise ConflictError(
                "Den Verein hat gerade jemand anders angelegt. Bitte noch einmal speichern."
            ) from exc
        raise


def _publish_new_club(index: PersonIndex, events: EventHub, club: Club | None) -> None:
    if club is not None:
        index.put_club(club.id, club.name)
        events.publish(EVENT_CLUB_CREATED, {"club_id": str(club.id)})


async def check_duplicates(
    session: AsyncSession, index: PersonIndex, name: str, club_id: UUID | None
) -> list[PersonOut]:
    """Mögliche Dubletten, wie sie `create_person` ohne `force` meldet (ohne Fehlerstatus)."""
    await _require_club(session, club_id)
    return await _persons_by_ids(session, index.duplicates(clean_text(name), club_id))


async def create_person(
    session: AsyncSession,
    index: PersonIndex,
    events: EventHub,
    data: PersonCreate,
    *,
    force: bool,
    may_create_club: ClubCreationCheck | None = None,
) -> PersonOut:
    """Legt die Person an; mit `club_name` samt Verein (gesucht oder neu, eine Transaktion)."""
    name = clean_text(data.name)
    new_club: Club | None = None
    try:
        club_id = data.club_id
        if data.club_name is not None:
            club, created = await _club_for_name(session, data.club_name, may_create_club)
            club_id = club.id
            new_club = club if created else None
        else:
            await _require_club(session, club_id)
        # In einem neuen Verein kann es keine Dublette geben.
        if not force and new_club is None:
            candidates = index.duplicates(name, club_id)
            if candidates:
                raise DuplicateError(
                    "Eine Person mit diesem Namen gibt es in diesem Verein schon. Ist es dieselbe "
                    "Person? Zum Anlegen trotzdem `force=true` mitschicken.",
                    await _persons_by_ids(session, candidates),
                )
        person = Person(
            name_enc=name,
            member_no_enc=data.member_no,
            club_id=club_id,
            display_mode=data.display_mode,
            show_club=data.show_club,
        )
        session.add(person)
        await _commit_person(session)
    except Exception:
        # Auch ein schon eingefügter neuer Verein verschwindet wieder.
        await session.rollback()
        raise
    _publish_new_club(index, events, new_club)
    index.put_person(person.id, name, data.member_no, club_id)
    events.publish(EVENT_PERSON_CREATED, {"person_id": str(person.id)})
    return await get_person(session, person.id)


async def update_person(
    session: AsyncSession,
    index: PersonIndex,
    events: EventHub,
    person_id: UUID,
    data: PersonUpdate,
    *,
    may_create_club: ClubCreationCheck | None = None,
) -> PersonOut:
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError("Diese Person gibt es nicht.")
    fields = data.model_fields_set
    new_club: Club | None = None
    try:
        if data.club_name is not None:
            club, created = await _club_for_name(session, data.club_name, may_create_club)
            person.club_id = club.id
            new_club = club if created else None
        elif "club_id" in fields:
            await _require_club(session, data.club_id)
            person.club_id = data.club_id
        if "name" in fields and data.name is not None:
            person.name_enc = clean_text(data.name)
        if "member_no" in fields:
            person.member_no_enc = data.member_no
        if "display_mode" in fields and data.display_mode is not None:
            person.display_mode = data.display_mode
        if "show_club" in fields and data.show_club is not None:
            person.show_club = data.show_club
        await _commit_person(session)
    except Exception:
        await session.rollback()
        raise
    _publish_new_club(index, events, new_club)
    index.put_person(person.id, person.name_enc, person.member_no_enc, person.club_id)
    events.publish(EVENT_PERSON_UPDATED, {"person_id": str(person.id)})
    return await get_person(session, person.id)


async def delete_person(
    session: AsyncSession, index: PersonIndex, events: EventHub, person_id: UUID
) -> None:
    """Löscht die Person endgültig (DSGVO Art. 17), sofern kein Modul widerspricht."""
    exists = await session.scalar(select(Person.id).where(Person.id == person_id))
    if exists is None:
        raise NotFoundError("Diese Person gibt es nicht.")
    reasons = await can_delete_person(session, person_id)
    if reasons:
        raise DeletionBlockedError(reasons)
    await session.execute(delete(Person).where(Person.id == person_id))
    await session.commit()
    index.remove_person(person_id)
    events.publish(EVENT_PERSON_DELETED, {"person_id": str(person_id)})


# --- Export und Import -------------------------------------------------------


async def export_persons_csv(session: AsyncSession) -> tuple[str, int]:
    """Alle Personen als CSV-Text, sortiert nach Name; dazu die Anzahl."""
    rows = await session.execute(
        select(Person, Club.name).outerjoin(Club, Club.id == Person.club_id)
    )
    export = sorted(
        (
            csvio.ExportRow(
                name=person.name_enc,
                club=club_name,
                member_no=person.member_no_enc,
                display_mode=person.display_mode,
                show_club=person.show_club,
            )
            for person, club_name in rows
        ),
        key=lambda row: (fold(row.name), fold(row.club or "")),
    )
    logger.info("Personen exportiert: %d.", len(export))
    return csvio.write_person_csv(export), len(export)


async def import_persons(
    session: AsyncSession,
    index: PersonIndex,
    events: EventHub,
    content: bytes,
    *,
    dry_run: bool,
    may_create_club: ClubCreationCheck | None = None,
) -> ImportReportOut:
    """Importiert Personen aus CSV. Fehlende Vereine werden angelegt.

    Je Zeile: `new` (wird angelegt), `duplicate` (gleicher Name im selben Verein, schon vorhanden
    oder weiter oben in der Datei; wird übersprungen) oder `error` (wird übersprungen).
    Vereine werden wie überall mit `names.fold` verglichen. Mit `dry_run` wird nichts
    gespeichert. Braucht das Übernehmen neue Vereine und verneint `may_create_club`, wird nichts
    importiert (`ClubCreationForbiddenError`); die Vorschau nennt neue Vereine trotzdem.
    """
    parsed = csvio.parse_person_csv(content)

    clubs_by_fold: dict[str, list[Club]] = {}
    for existing in await session.scalars(select(Club).order_by(func.lower(Club.name), Club.id)):
        clubs_by_fold.setdefault(fold(existing.name), []).append(existing)
    new_clubs: dict[str, Club] = {}
    seen_in_file: set[tuple[str, str | None]] = set()
    report: list[ImportRowOut] = []
    to_create: list[tuple[int, Person, str | None]] = []

    for row in parsed.rows:
        if isinstance(row, csvio.ImportRowError):
            report.append(
                ImportRowOut(
                    line=row.line,
                    status="error",
                    message=row.message,
                    name=row.name,
                    club=row.club,
                )
            )
            continue
        club_key = fold(row.club) if row.club else None
        existing_club = (
            _pick_club(clubs_by_fold.get(club_key, []), row.club) if club_key and row.club else None
        )
        club_id = existing_club.id if existing_club else None
        file_key = (fold(row.name), club_key)
        if file_key in seen_in_file:
            report.append(
                ImportRowOut(
                    line=row.line,
                    status="duplicate",
                    message="Dieselbe Person steht weiter oben in der Datei.",
                    name=row.name,
                    club=row.club,
                )
            )
            continue
        # Dubletten in der Datenbank kann es nur in vorhandenen Vereinen (oder ohne Verein) geben.
        candidates = index.duplicates(row.name, club_id) if (club_key is None or club_id) else []
        if candidates:
            report.append(
                ImportRowOut(
                    line=row.line,
                    status="duplicate",
                    message="Eine Person mit diesem Namen gibt es in diesem Verein schon.",
                    person_id=candidates[0],
                    name=row.name,
                    club=row.club,
                )
            )
            continue
        seen_in_file.add(file_key)
        club: Club | None = None
        if club_key is not None and club_id is None:
            club = new_clubs.get(club_key)
            if club is None:
                club = Club(name=row.club)
                new_clubs[club_key] = club
        person = Person(
            name_enc=row.name,
            member_no_enc=row.member_no,
            club_id=club_id,
            display_mode=row.display_mode,
            show_club=row.show_club,
        )
        to_create.append((len(report), person, club_key if club is not None else None))
        report.append(ImportRowOut(line=row.line, status="new", name=row.name, club=row.club))

    if not dry_run and new_clubs and may_create_club is not None and not await may_create_club():
        missing = sorted((club.name for club in new_clubs.values()), key=str.casefold)
        quoted = ", ".join(f"„{name}“" for name in missing)
        lead = (
            f"Den Verein {quoted} gibt es noch nicht."
            if len(missing) == 1
            else f"Diese Vereine gibt es noch nicht: {quoted}."
        )
        raise ClubCreationForbiddenError(
            f"{lead} Neue Vereine anlegen darf nur, wer die Berechtigung „club.edit“ hat. Es "
            "wurde nichts importiert. Bitte die Vereine zuerst anlegen lassen oder in der Datei "
            "vorhandene Vereine eintragen."
        )

    if not dry_run and to_create:
        session.add_all(new_clubs.values())
        await session.flush()
        for _, person, new_club_key in to_create:
            if new_club_key is not None:
                person.club_id = new_clubs[new_club_key].id
        session.add_all(person for _, person, _ in to_create)
        await session.commit()
        for club in new_clubs.values():
            index.put_club(club.id, club.name)
            events.publish(EVENT_CLUB_CREATED, {"club_id": str(club.id)})
        for position, person, _ in to_create:
            index.put_person(person.id, person.name_enc, person.member_no_enc, person.club_id)
            report[position] = report[position].model_copy(update={"person_id": person.id})
        events.publish(
            EVENT_PERSON_IMPORTED, {"person_ids": [str(person.id) for _, person, _ in to_create]}
        )

    counts = {
        status: sum(1 for row in report if row.status == status)
        for status in ("new", "duplicate", "error")
    }
    logger.info(
        "Personen-Import%s: %d neu, %d Dubletten, %d Fehler.",
        " (Vorschau)" if dry_run else "",
        counts["new"],
        counts["duplicate"],
        counts["error"],
    )
    return ImportReportOut(
        dry_run=dry_run,
        new=counts["new"],
        duplicate=counts["duplicate"],
        error=counts["error"],
        new_clubs=sorted((club.name for club in new_clubs.values()), key=str.casefold),
        ignored_columns=parsed.ignored_columns,
        rows=report,
    )
