"""HTTP-Schnittstelle der Teilnehmer: Vereine und Personen."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.db import SessionDep
from app.core.events import EventHubDep
from app.core.security import require
from app.modules.teilnehmer import service
from app.modules.teilnehmer.csvio import ImportFormatError
from app.modules.teilnehmer.index import PersonIndex
from app.modules.teilnehmer.schemas import (
    ClubCreate,
    ClubMerge,
    ClubOut,
    ClubUpdate,
    DuplicateCheckOut,
    DuplicateOut,
    ImportReportOut,
    PersonCheck,
    PersonCreate,
    PersonOut,
    PersonUpdate,
)

router = APIRouter(tags=["teilnehmer"])

IMPORT_MAX_BYTES = 5 * 1024 * 1024


def get_person_index(request: Request) -> PersonIndex:
    return request.app.state.person_index


IndexDep = Annotated[PersonIndex, Depends(get_person_index)]

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Nicht vorhanden"}}
CONFLICT = {status.HTTP_409_CONFLICT: {"description": "Widerspricht dem Datenbestand"}}
UNPROCESSABLE = {status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Ungültige Eingabe"}}


_ERROR_STATUS: dict[type[Exception], int] = {
    service.NotFoundError: status.HTTP_404_NOT_FOUND,
    service.InvalidReferenceError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    service.ConflictError: status.HTTP_409_CONFLICT,
    service.DeletionBlockedError: status.HTTP_409_CONFLICT,
}
DomainErrors = tuple(_ERROR_STATUS)


def _http(exc: Exception) -> HTTPException:
    return HTTPException(status_code=_ERROR_STATUS[type(exc)], detail=str(exc))


# --- Vereine -----------------------------------------------------------------


@router.get(
    "/clubs",
    summary="Vereine",
    description=(
        "Ohne `q` alle Vereine nach Name. Mit `q` Suche in Name und Kürzel, ohne Groß-/"
        "Kleinschreibung und Umlaut-Schreibweise; Treffer am Anfang stehen vorn."
    ),
    dependencies=[Depends(require("person.read"))],
)
async def list_clubs(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200, description="Suchbegriff")] = None,
) -> list[ClubOut]:
    return await service.list_clubs(session, q)


@router.post(
    "/clubs",
    summary="Verein anlegen",
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    dependencies=[Depends(require("club.edit"))],
)
async def create_club(
    data: ClubCreate, session: SessionDep, index: IndexDep, events: EventHubDep
) -> ClubOut:
    try:
        return await service.create_club(session, index, events, data)
    except DomainErrors as exc:
        raise _http(exc) from exc


@router.get(
    "/clubs/{club_id}",
    summary="Verein",
    responses=NOT_FOUND,
    dependencies=[Depends(require("person.read"))],
)
async def get_club(club_id: UUID, session: SessionDep) -> ClubOut:
    try:
        return await service.get_club(session, club_id)
    except DomainErrors as exc:
        raise _http(exc) from exc


@router.patch(
    "/clubs/{club_id}",
    summary="Verein ändern",
    responses=NOT_FOUND | CONFLICT,
    dependencies=[Depends(require("club.edit"))],
)
async def update_club(
    club_id: UUID, data: ClubUpdate, session: SessionDep, index: IndexDep, events: EventHubDep
) -> ClubOut:
    try:
        return await service.update_club(session, index, events, club_id, data)
    except DomainErrors as exc:
        raise _http(exc) from exc


@router.delete(
    "/clubs/{club_id}",
    summary="Verein löschen (nur ohne Personen)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
    dependencies=[Depends(require("club.edit"))],
)
async def delete_club(
    club_id: UUID, session: SessionDep, index: IndexDep, events: EventHubDep
) -> None:
    try:
        await service.delete_club(session, index, events, club_id)
    except DomainErrors as exc:
        raise _http(exc) from exc


@router.post(
    "/clubs/{club_id}/merge",
    summary="Verein in einen anderen zusammenführen",
    description=(
        "Hängt alle Personen des Vereins aus dem Pfad an den Verein `into_id` und löscht "
        "danach den Verein aus dem Pfad. Liefert den Zielverein."
    ),
    responses=NOT_FOUND | CONFLICT | UNPROCESSABLE,
    dependencies=[Depends(require("club.edit"))],
)
async def merge_club(
    club_id: UUID, data: ClubMerge, session: SessionDep, index: IndexDep, events: EventHubDep
) -> ClubOut:
    try:
        return await service.merge_clubs(session, index, events, club_id, data.into_id)
    except DomainErrors as exc:
        raise _http(exc) from exc


# --- Personen ----------------------------------------------------------------


@router.get(
    "/persons",
    summary="Personen auflisten oder suchen",
    description=(
        "Ohne `q` alle Personen nach Name. Mit `q` Suche in Name, Mitgliedsnummer und "
        "Vereinsname, ohne Groß-/Kleinschreibung und Umlaut-Schreibweise („koehler“ findet "
        "„Köhler“). Treffer am Anfang eines Felds stehen vor Teiltreffern. Die Gesamtzahl steht "
        "im Header `X-Total-Count`."
    ),
    dependencies=[Depends(require("person.read"))],
)
async def list_persons(
    session: SessionDep,
    index: IndexDep,
    response: Response,
    q: Annotated[str | None, Query(max_length=200, description="Suchbegriff")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PersonOut]:
    persons, total = await service.list_persons(session, index, q, limit, offset)
    response.headers["X-Total-Count"] = str(total)
    return persons


@router.post(
    "/persons",
    summary="Person anlegen",
    description=(
        "Gibt es im selben Verein schon eine Person mit gleicher Schreibweise des Namens "
        "(ohne Groß-/Kleinschreibung, Akzente und Umlaut-Schreibweise), kommt 409 mit den "
        "Kandidaten. Mit `force=true` wird trotzdem angelegt."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=PersonOut,
    responses={status.HTTP_409_CONFLICT: {"model": DuplicateOut}} | UNPROCESSABLE,
    dependencies=[Depends(require("person.edit"))],
)
async def create_person(
    data: PersonCreate,
    session: SessionDep,
    index: IndexDep,
    events: EventHubDep,
    force: Annotated[bool, Query(description="Dubletten-Hinweis übergehen")] = False,
) -> PersonOut | JSONResponse:
    try:
        return await service.create_person(session, index, events, data, force=force)
    except service.DuplicateError as exc:
        body = DuplicateOut(detail=str(exc), candidates=exc.candidates)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content=body.model_dump(mode="json")
        )
    except DomainErrors as exc:
        raise _http(exc) from exc


@router.post(
    "/persons/check",
    summary="Vor dem Anlegen auf Dubletten prüfen",
    description=(
        "Dieselbe Prüfung wie `POST /persons`, aber ohne Fehlerstatus und ohne etwas anzulegen: "
        "`duplicates` nennt Personen mit gleicher Schreibweise des Namens im selben Verein "
        "(leer: keine Dublette). Unbekannter Verein: 422."
    ),
    responses=UNPROCESSABLE,
    dependencies=[Depends(require("person.read"))],
)
async def check_person(
    data: PersonCheck, session: SessionDep, index: IndexDep
) -> DuplicateCheckOut:
    try:
        duplicates = await service.check_duplicates(session, index, data.name, data.club_id)
    except DomainErrors as exc:
        raise _http(exc) from exc
    return DuplicateCheckOut(duplicates=duplicates)


@router.get(
    "/persons/export.csv",
    summary="Alle Personen als CSV",
    description="UTF-8 mit BOM, Trennzeichen `;`. Lässt sich unverändert wieder importieren.",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
    dependencies=[Depends(require("person.export"))],
)
async def export_persons(session: SessionDep) -> Response:
    content, _ = await service.export_persons_csv(session)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="personen.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/persons/import",
    summary="Personen aus CSV importieren",
    description=(
        "Rohinhalt der CSV-Datei als Anfragekörper (`Content-Type: text/csv`). UTF-8 mit oder "
        "ohne BOM; ist die Datei kein gültiges UTF-8, wird sie als Windows-1252 gelesen (Excel "
        "„CSV (Trennzeichen-getrennt)“). Trennzeichen `;`, `,` oder Tabulator. Spalten: "
        "`name`/`Name` (Pflicht; alternativ `Vorname` und `Nachname`/`Name`/`Familienname`, "
        "zusammengesetzt zu „Vorname Nachname“), `club`/`Verein`/`Vereinsname`, "
        "`member_no`/`Mitgliedsnummer`, `display_mode`/`Anzeige`, `show_club`/`Verein anzeigen` "
        "(ohne Rücksicht auf Groß-/Kleinschreibung, Leerzeichen und Umlaut-Schreibweise). Andere "
        "Spalten werden ignoriert, nicht gespeichert und in `ignored_columns` genannt. "
        "Fehlende Vereine werden angelegt, Dubletten und fehlerhafte Zeilen übersprungen. "
        "Mit `dry_run=true` wird nur geprüft."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Datei unbrauchbar"},
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "Datei zu groß"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string"}}},
        }
    },
    dependencies=[Depends(require("person.edit"))],
)
async def import_persons(
    request: Request,
    session: SessionDep,
    index: IndexDep,
    events: EventHubDep,
    dry_run: Annotated[bool, Query(description="Nur prüfen, nichts speichern")] = False,
) -> ImportReportOut:
    content = await request.body()
    if len(content) > IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Die Datei ist größer als 5 MB.",
        )
    try:
        return await service.import_persons(session, index, events, content, dry_run=dry_run)
    except ImportFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/persons/{person_id}",
    summary="Person",
    responses=NOT_FOUND,
    dependencies=[Depends(require("person.read"))],
)
async def get_person(person_id: UUID, session: SessionDep) -> PersonOut:
    try:
        return await service.get_person(session, person_id)
    except DomainErrors as exc:
        raise _http(exc) from exc


@router.patch(
    "/persons/{person_id}",
    summary="Person ändern",
    responses=NOT_FOUND | UNPROCESSABLE,
    dependencies=[Depends(require("person.edit"))],
)
async def update_person(
    person_id: UUID, data: PersonUpdate, session: SessionDep, index: IndexDep, events: EventHubDep
) -> PersonOut:
    try:
        return await service.update_person(session, index, events, person_id, data)
    except DomainErrors as exc:
        raise _http(exc) from exc


@router.delete(
    "/persons/{person_id}",
    summary="Person endgültig löschen",
    description=(
        "Löscht die Person unwiderruflich (Recht auf Löschung, Art. 17 DSGVO). Andere Module "
        "können widersprechen, etwa solange die Person in einem Turnier angemeldet ist; dann "
        "kommt 409 mit der Begründung."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
    dependencies=[Depends(require("person.delete"))],
)
async def delete_person(
    person_id: UUID, session: SessionDep, index: IndexDep, events: EventHubDep
) -> None:
    try:
        await service.delete_person(session, index, events, person_id)
    except DomainErrors as exc:
        raise _http(exc) from exc
