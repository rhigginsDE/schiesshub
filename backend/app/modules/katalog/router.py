"""HTTP-Schnittstelle des Katalogs (nur lesend)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.core.db import SessionDep
from app.modules.katalog import service
from app.modules.katalog.schemas import (
    DisziplinDetailOut,
    DisziplinOut,
    GruppeOut,
    KlasseOut,
    VerbandOut,
)

router = APIRouter(prefix="/katalog", tags=["katalog"])

VerbandQuery = Annotated[
    str | None, Query(description="Verband, z. B. `bds`. Ohne Angabe: alle Verbände.")
]
NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Eintrag nicht im Katalog"}}


def _not_found(exc: service.NotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/verbaende", summary="Verbände mit Katalog")
async def verbaende(session: SessionDep) -> list[VerbandOut]:
    return await service.list_federations(session)


@router.get("/gruppen", summary="Disziplingruppen", responses=NOT_FOUND)
async def gruppen(session: SessionDep, verband: VerbandQuery = None) -> list[GruppeOut]:
    try:
        return await service.list_groups(session, verband)
    except service.NotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/disziplinen", summary="Disziplinen suchen", responses=NOT_FOUND)
async def disziplinen(
    session: SessionDep,
    verband: VerbandQuery = None,
    gruppe: Annotated[str | None, Query(description="ID einer Gruppe")] = None,
    q: Annotated[str | None, Query(description="Suche in Kennziffer und Name")] = None,
) -> list[DisziplinOut]:
    try:
        return await service.list_disciplines(session, verband, gruppe, q)
    except service.NotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/disziplinen/{verband}/{kennziffer}",
    summary="Disziplin mit Ablauf und Wertung",
    responses=NOT_FOUND,
    # Felder, die im Katalog nicht gesetzt sind (z. B. in Abschnitten), fehlen in der Antwort.
    response_model_exclude_unset=True,
)
async def disziplin(session: SessionDep, verband: str, kennziffer: str) -> DisziplinDetailOut:
    try:
        return await service.get_discipline(session, verband, kennziffer)
    except service.NotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/klassen", summary="Wettbewerbsklassen", responses=NOT_FOUND)
async def klassen(session: SessionDep, verband: VerbandQuery = None) -> list[KlasseOut]:
    try:
        return await service.list_classes(session, verband)
    except service.NotFoundError as exc:
        raise _not_found(exc) from exc
