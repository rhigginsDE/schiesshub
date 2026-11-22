"""HTTP-Schnittstelle des Moduls `turnier`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response, status

from app.core.db import SessionDep
from app.core.events import EventHubDep
from app.core.security import Actor, require
from app.modules.turnier import announcement, service
from app.modules.turnier.schemas import (
    Announcement,
    AnnouncementDocument,
    CatalogDiffOut,
    ClassCreate,
    ClassImport,
    ClassOut,
    ClassUpdate,
    CompetitionCreate,
    CompetitionOut,
    CompetitionUpdate,
    DefinitionReset,
    Order,
    RangeCreate,
    RangeOut,
    RangeUpdate,
    RevisionOut,
    StatusChange,
    TournamentCreate,
    TournamentOut,
    TournamentOverview,
    TournamentUpdate,
)

PERMISSION_READ = "tournament.read"
PERMISSION_EDIT = "tournament.edit"
PERMISSION_REOPEN = "tournament.reopen"

Reader = Annotated[Actor, Depends(require(PERMISSION_READ))]
Editor = Annotated[Actor, Depends(require(PERMISSION_EDIT))]

router = APIRouter(prefix="/tournaments", tags=["turnier"])

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Nicht gefunden"}}
CONFLICT = {status.HTTP_409_CONFLICT: {"description": "Im aktuellen Zustand nicht möglich"}}
WRITE = {**NOT_FOUND, **CONFLICT}
# Nicht gesetzte Katalogfelder in `definition` fehlen in der Antwort, wie im Katalog.
COMPETITION_RESPONSE = {"response_model_exclude_unset": True}

TOURNAMENT = "/{tournament_id}"
RANGES = "/{tournament_id}/ranges"
CLASSES = "/{tournament_id}/classes"
COMPETITIONS = "/{tournament_id}/competitions"
COMPETITION = "/{tournament_id}/competitions/{competition_id}"


def _competition(item: object) -> CompetitionOut:
    return CompetitionOut.model_validate(item)


# --- Turnier -----------------------------------------------------------------


@router.get("", summary="Alle Turniere")
async def list_tournaments(session: SessionDep, _: Reader) -> list[TournamentOut]:
    return [TournamentOut.model_validate(t) for t in await service.list_tournaments(session)]


@router.post("", summary="Turnier anlegen", status_code=status.HTTP_201_CREATED)
async def create_tournament(
    data: TournamentCreate, session: SessionDep, events: EventHubDep, _: Editor
) -> TournamentOut:
    return TournamentOut.model_validate(await service.create_tournament(session, events, data))


@router.get(TOURNAMENT, summary="Turnier", responses=NOT_FOUND)
async def get_tournament(tournament_id: UUID, session: SessionDep, _: Reader) -> TournamentOut:
    return TournamentOut.model_validate(await service.get_tournament(session, tournament_id))


@router.patch(TOURNAMENT, summary="Turnier ändern", responses=WRITE)
async def update_tournament(
    tournament_id: UUID,
    data: TournamentUpdate,
    session: SessionDep,
    events: EventHubDep,
    _: Editor,
) -> TournamentOut:
    tournament = await service.update_tournament(session, events, tournament_id, data)
    return TournamentOut.model_validate(tournament)


@router.post(
    f"{TOURNAMENT}/status",
    summary="Status wechseln",
    description=(
        "Schrittweise: `draft` → `active` → `closed`. Zurück verlangt zusätzlich die "
        f"Berechtigung `{PERMISSION_REOPEN}`."
    ),
    responses=WRITE,
)
async def change_status(
    tournament_id: UUID,
    data: StatusChange,
    request: Request,
    session: SessionDep,
    events: EventHubDep,
    _: Editor,
) -> TournamentOut:
    async def authorize_reopen() -> Actor:
        return await require(PERMISSION_REOPEN)(request)

    tournament = await service.change_status(
        session, events, tournament_id, data.status, authorize_reopen
    )
    return TournamentOut.model_validate(tournament)


@router.delete(
    TOURNAMENT,
    summary="Turnier löschen (nur im Entwurf)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=WRITE,
)
async def delete_tournament(
    tournament_id: UUID, session: SessionDep, events: EventHubDep, _: Editor
) -> Response:
    await service.delete_tournament(session, events, tournament_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    f"{TOURNAMENT}/overview",
    summary="Turnier mit Ständen, Klassen und Wettbewerben",
    responses=NOT_FOUND,
    **COMPETITION_RESPONSE,
)
async def get_overview(tournament_id: UUID, session: SessionDep, _: Reader) -> TournamentOverview:
    tournament, ranges, classes, competitions = await service.get_overview(session, tournament_id)
    return TournamentOverview.model_validate(
        {
            **TournamentOut.model_validate(tournament).model_dump(),
            "ranges": [RangeOut.model_validate(item) for item in ranges],
            "classes": [ClassOut.model_validate(item) for item in classes],
            "competitions": [_competition(item) for item in competitions],
        }
    )


# --- Ausschreibung ------------------------------------------------------------


@router.get(f"{TOURNAMENT}/announcement", summary="Ausschreibung", responses=NOT_FOUND)
async def get_announcement(tournament_id: UUID, session: SessionDep, _: Reader) -> Announcement:
    return await announcement.get_announcement(session, tournament_id)


@router.put(
    f"{TOURNAMENT}/announcement",
    summary="Ausschreibung speichern",
    description=(
        "Ersetzt die Ausschreibung als Ganzes. Auch im laufenden Turnier änderbar, nicht mehr "
        "nach dem Abschluss. Texte sind reiner Text (Absätze mit Leerzeilen), kein HTML."
    ),
    responses=WRITE,
)
async def put_announcement(
    tournament_id: UUID,
    data: Announcement,
    session: SessionDep,
    events: EventHubDep,
    _: Editor,
) -> Announcement:
    return await announcement.put_announcement(session, events, tournament_id, data)


@router.get(
    f"{TOURNAMENT}/announcement/document",
    summary="Ausschreibung zum Drucken",
    description=(
        "Sichtbare Bausteine in ihrer Reihenfolge; automatische Bausteine bringen die aktuellen "
        "Turnierdaten mit. Enthält keine Teilnehmerdaten."
    ),
    responses=NOT_FOUND,
)
async def get_announcement_document(
    tournament_id: UUID, session: SessionDep, _: Reader
) -> AnnouncementDocument:
    return await announcement.build_document(session, tournament_id)


# --- Stand -------------------------------------------------------------------


@router.get(RANGES, summary="Stände", responses=NOT_FOUND)
async def list_ranges(tournament_id: UUID, session: SessionDep, _: Reader) -> list[RangeOut]:
    return [RangeOut.model_validate(r) for r in await service.list_ranges(session, tournament_id)]


@router.post(RANGES, summary="Stand anlegen", status_code=status.HTTP_201_CREATED, responses=WRITE)
async def create_range(
    tournament_id: UUID,
    data: RangeCreate,
    session: SessionDep,
    events: EventHubDep,
    _: Editor,
) -> RangeOut:
    return RangeOut.model_validate(await service.create_range(session, events, tournament_id, data))


@router.put(f"{RANGES}/order", summary="Stände sortieren", responses=WRITE)
async def reorder_ranges(
    tournament_id: UUID, data: Order, session: SessionDep, events: EventHubDep, _: Editor
) -> list[RangeOut]:
    items = await service.reorder_ranges(session, events, tournament_id, data.ids)
    return [RangeOut.model_validate(item) for item in items]


@router.get(f"{RANGES}/{{range_id}}", summary="Stand", responses=NOT_FOUND)
async def get_range(
    tournament_id: UUID, range_id: UUID, session: SessionDep, _: Reader
) -> RangeOut:
    return RangeOut.model_validate(await service.get_range(session, tournament_id, range_id))


@router.patch(f"{RANGES}/{{range_id}}", summary="Stand ändern", responses=WRITE)
async def update_range(
    tournament_id: UUID,
    range_id: UUID,
    data: RangeUpdate,
    session: SessionDep,
    events: EventHubDep,
    _: Editor,
) -> RangeOut:
    return RangeOut.model_validate(
        await service.update_range(session, events, tournament_id, range_id, data)
    )


@router.delete(
    f"{RANGES}/{{range_id}}",
    summary="Stand löschen",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=WRITE,
)
async def delete_range(
    tournament_id: UUID, range_id: UUID, session: SessionDep, events: EventHubDep, _: Editor
) -> Response:
    await service.delete_range(session, events, tournament_id, range_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Klasse ------------------------------------------------------------------


@router.get(CLASSES, summary="Klassen", responses=NOT_FOUND)
async def list_classes(tournament_id: UUID, session: SessionDep, _: Reader) -> list[ClassOut]:
    return [ClassOut.model_validate(c) for c in await service.list_classes(session, tournament_id)]


@router.post(
    CLASSES, summary="Klasse anlegen", status_code=status.HTTP_201_CREATED, responses=WRITE
)
async def create_class(
    tournament_id: UUID,
    data: ClassCreate,
    session: SessionDep,
    events: EventHubDep,
    _: Editor,
) -> ClassOut:
    return ClassOut.model_validate(await service.create_class(session, events, tournament_id, data))


@router.post(
    f"{CLASSES}/import",
    summary="Klassen aus dem Katalog übernehmen",
    description=(
        "Kopiert die Klassen des Verbands. Klassen mit einem Kürzel, das es im Turnier schon "
        "gibt, bleiben unverändert. Antwort: die neu angelegten Klassen."
    ),
    status_code=status.HTTP_201_CREATED,
    responses=WRITE,
)
async def import_classes(
    tournament_id: UUID,
    data: ClassImport,
    session: SessionDep,
    events: EventHubDep,
    _: Editor,
) -> list[ClassOut]:
    items = await service.import_classes(session, events, tournament_id, data.federation)
    return [ClassOut.model_validate(item) for item in items]


@router.put(f"{CLASSES}/order", summary="Klassen sortieren", responses=WRITE)
async def reorder_classes(
    tournament_id: UUID, data: Order, session: SessionDep, events: EventHubDep, _: Editor
) -> list[ClassOut]:
    items = await service.reorder_classes(session, events, tournament_id, data.ids)
    return [ClassOut.model_validate(item) for item in items]


@router.get(f"{CLASSES}/{{class_id}}", summary="Klasse", responses=NOT_FOUND)
async def get_class(
    tournament_id: UUID, class_id: UUID, session: SessionDep, _: Reader
) -> ClassOut:
    return ClassOut.model_validate(await service.get_class(session, tournament_id, class_id))


@router.patch(f"{CLASSES}/{{class_id}}", summary="Klasse ändern", responses=WRITE)
async def update_class(
    tournament_id: UUID,
    class_id: UUID,
    data: ClassUpdate,
    session: SessionDep,
    events: EventHubDep,
    _: Editor,
) -> ClassOut:
    return ClassOut.model_validate(
        await service.update_class(session, events, tournament_id, class_id, data)
    )


@router.delete(
    f"{CLASSES}/{{class_id}}",
    summary="Klasse löschen",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=WRITE,
)
async def delete_class(
    tournament_id: UUID, class_id: UUID, session: SessionDep, events: EventHubDep, _: Editor
) -> Response:
    await service.delete_class(session, events, tournament_id, class_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Wettbewerb --------------------------------------------------------------


@router.get(COMPETITIONS, summary="Wettbewerbe", responses=NOT_FOUND, **COMPETITION_RESPONSE)
async def list_competitions(
    tournament_id: UUID, session: SessionDep, _: Reader
) -> list[CompetitionOut]:
    return [_competition(c) for c in await service.list_competitions(session, tournament_id)]


@router.post(
    COMPETITIONS,
    summary="Wettbewerb anlegen",
    description=(
        "Aus dem Katalog mit `catalog_federation` und `catalog_code` (optional `variant_id`) "
        "oder als eigener Wettbewerb mit vollständiger `definition`. Nicht angegebene Felder "
        "kommen aus den Turnier-Einstellungen; `planning` und `heat_minutes` leitet der Server "
        "aus dem Ablauf ab."
    ),
    status_code=status.HTTP_201_CREATED,
    responses=WRITE,
    **COMPETITION_RESPONSE,
)
async def create_competition(
    tournament_id: UUID,
    data: CompetitionCreate,
    session: SessionDep,
    events: EventHubDep,
    actor: Editor,
) -> CompetitionOut:
    return _competition(
        await service.create_competition(session, events, tournament_id, data, actor)
    )


@router.put(
    f"{COMPETITIONS}/order",
    summary="Wettbewerbe sortieren",
    responses=WRITE,
    **COMPETITION_RESPONSE,
)
async def reorder_competitions(
    tournament_id: UUID, data: Order, session: SessionDep, events: EventHubDep, _: Editor
) -> list[CompetitionOut]:
    items = await service.reorder_competitions(session, events, tournament_id, data.ids)
    return [_competition(item) for item in items]


@router.get(
    f"{COMPETITIONS}/{{competition_id}}",
    summary="Wettbewerb",
    responses=NOT_FOUND,
    **COMPETITION_RESPONSE,
)
async def get_competition(
    tournament_id: UUID, competition_id: UUID, session: SessionDep, _: Reader
) -> CompetitionOut:
    return _competition(await service.get_competition(session, tournament_id, competition_id))


@router.patch(
    f"{COMPETITIONS}/{{competition_id}}",
    summary="Wettbewerb ändern",
    description=(
        "Änderungen an den wertungsrelevanten Feldern (`definition`, `capture_mode`, "
        "`multi_start`, `max_starts`, `multi_start_rule`, `combined_ranking`) legen eine neue "
        "Revision an und melden `competition.definition_changed`. Sie sind auch im laufenden "
        "Turnier erlaubt, verlangen dann aber `reason`. `definition` wird als Ganzes ersetzt; "
        "ein weggelassenes optionales Feld ist danach entfernt."
    ),
    responses=WRITE,
    **COMPETITION_RESPONSE,
)
async def update_competition(
    tournament_id: UUID,
    competition_id: UUID,
    data: CompetitionUpdate,
    session: SessionDep,
    events: EventHubDep,
    actor: Editor,
) -> CompetitionOut:
    return _competition(
        await service.update_competition(
            session, events, tournament_id, competition_id, data, actor
        )
    )


@router.post(
    f"{COMPETITIONS}/{{competition_id}}/reset-definition",
    summary="Definition auf den Katalogwert zurücksetzen",
    responses=WRITE,
    **COMPETITION_RESPONSE,
)
async def reset_definition(
    tournament_id: UUID,
    competition_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: Editor,
    data: DefinitionReset | None = None,
) -> CompetitionOut:
    data = data or DefinitionReset()
    return _competition(
        await service.reset_definition(
            session, events, tournament_id, competition_id, data.variant_id, actor, data.reason
        )
    )


@router.get(
    f"{COMPETITION}/revisions",
    summary="Revisionen der Wertung",
    description="Alle Stände der wertungsrelevanten Felder, die älteste zuerst.",
    responses=NOT_FOUND,
    **COMPETITION_RESPONSE,
)
async def list_revisions(
    tournament_id: UUID, competition_id: UUID, session: SessionDep, _: Reader
) -> list[RevisionOut]:
    items = await service.list_revisions(session, tournament_id, competition_id)
    return [RevisionOut.model_validate(item) for item in items]


@router.get(
    f"{COMPETITION}/revisions/{{revision}}",
    summary="Eine Revision der Wertung",
    responses=NOT_FOUND,
    **COMPETITION_RESPONSE,
)
async def get_revision(
    tournament_id: UUID,
    competition_id: UUID,
    revision: Annotated[int, Path(ge=1)],
    session: SessionDep,
    _: Reader,
) -> RevisionOut:
    item = await service.get_revision(session, tournament_id, competition_id, revision)
    return RevisionOut.model_validate(item)


@router.get(
    f"{COMPETITION}/catalog-diff",
    summary="Abweichungen vom Katalog",
    description=(
        "Vergleicht die aktuelle Definition mit der Katalog-Variante, aus der sie stammt "
        "(aktueller Katalogstand). `deviates` kennzeichnet „abweichend vom Katalog“. "
        "Ohne Katalogherkunft ist die Liste leer."
    ),
    responses=NOT_FOUND,
)
async def get_catalog_diff(
    tournament_id: UUID, competition_id: UUID, session: SessionDep, _: Reader
) -> CatalogDiffOut:
    return await service.get_catalog_diff(session, tournament_id, competition_id)


@router.delete(
    f"{COMPETITIONS}/{{competition_id}}",
    summary="Wettbewerb löschen",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=WRITE,
)
async def delete_competition(
    tournament_id: UUID,
    competition_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    _: Editor,
) -> Response:
    await service.delete_competition(session, events, tournament_id, competition_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
