"""HTTP-Schnittstelle des Moduls `export`: Startliste, Ergebnisliste und Ergebnisse als Datei.

Die Pfade der Ergebnisliste heißen aus Kompatibilität weiter `winners.pdf`/`winners.csv`; der
Dateiname im Download lautet „…_Ergebnisliste_….pdf“.

Alle Endpunkte brauchen `export.read`. `names=full` (voller Name und Verein für den internen
Gebrauch, unabhängig von der Anzeige-Einstellung) braucht zusätzlich `export.full_names`.
Standard ist `names=public`: Namen so, wie die Person es gewählt hat (voll, abgekürzt oder nur
die Startnummer), der Verein nur mit `show_club`.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BeforeValidator, Field

from app.core.db import SessionDep
from app.core.security import Actor, require
from app.modules.ergebnisse import begriffe
from app.modules.export import service, tables
from app.modules.export.csvout import write_csv
from app.modules.export.formatting import file_name
from app.modules.export.pdfout import render_pdf
from app.modules.export.records import Meta, NamesMode, StartlistSort

PERMISSION_READ = "export.read"
PERMISSION_FULL_NAMES = "export.full_names"

Reader = Annotated[Actor, Depends(require(PERMISSION_READ))]


def _empty_is_none(value: Any) -> Any:
    """`?top=` oder `?class_id=` ohne Wert heißt: nicht gesetzt."""
    return None if value == "" else value


OptionalId = Annotated[UUID | None, BeforeValidator(_empty_is_none), Query()]
Names = Annotated[
    NamesMode,
    Query(description="`public` (Standard): nach Anzeige-Einstellung; `full`: voller Name."),
]
Top = Annotated[
    Annotated[int, Field(ge=1)] | None,
    BeforeValidator(_empty_is_none),
    Query(description="Nur die ersten Plätze (geteilte Plätze vollständig); leer = alle."),
]

IncludeAborted = Annotated[
    bool,
    Query(
        description="Abgebrochene Starts ohne Platz am Ende aufführen (Standard: ja). Ein "
        "Abbruch nach dem Kommando „Feuer“ mit Platz steht immer in der Liste."
    ),
]

router = APIRouter(prefix="/tournaments/{tournament_id}/export", tags=["export"])

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Nicht gefunden"}}
FORBIDDEN = {status.HTTP_403_FORBIDDEN: {"description": "Berechtigung fehlt"}}
PDF = {
    200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}},
    **NOT_FOUND,
    **FORBIDDEN,
}
CSV = {
    200: {"content": {"text/csv": {"schema": {"type": "string"}}}},
    **NOT_FOUND,
    **FORBIDDEN,
}

FULL_NAMES_DENIED = (
    "Volle Namen darf nur exportieren, wer die Berechtigung „export.full_names“ hat. Ohne sie "
    "steht jede Person so in der Liste, wie sie es gewählt hat (names=public)."
)


async def _check_names(request: Request, names: NamesMode) -> None:
    if names != "full":
        return
    try:
        await require(PERMISSION_FULL_NAMES)(request)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, FULL_NAMES_DENIED) from exc
        raise


def _file(content: bytes, media_type: str, name: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            # Personenbezogene Listen nicht in Zwischenspeichern ablegen.
            "Cache-Control": "no-store",
        },
    )


def _pdf(report: tables.Report, meta: Meta, kind: str) -> Response:
    return _file(
        render_pdf(report),
        "application/pdf",
        file_name(meta.tournament_name, kind, meta.date_from, "pdf"),
    )


def _csv(sheet: tables.Sheet, meta: Meta, kind: str) -> Response:
    return _file(
        write_csv(sheet),
        "text/csv; charset=utf-8",
        file_name(meta.tournament_name, kind, meta.date_from, "csv"),
    )


# --- Startliste ----------------------------------------------------------------------------

STARTLIST_DESCRIPTION = (
    "Alle Starts, wahlweise eines Wettbewerbs (`competition_id`) oder Schießstands "
    "(`range_id`). `sort`: `competition` (je Wettbewerb in der Reihenfolge am Schießstand), "
    "`start_number` oder `range` (je Schießstand nach Uhrzeit und Schützenstand)."
)


async def _startlist(
    request: Request,
    session: SessionDep,
    tournament_id: UUID,
    competition_id: UUID | None,
    range_id: UUID | None,
    names: NamesMode,
) -> tuple[Meta, list[Any]]:
    await _check_names(request, names)
    records = await service.startlist(
        session, tournament_id, competition_id=competition_id, range_id=range_id, names=names
    )
    return await service.meta(session, tournament_id, names), records


@router.get(
    "/startlist.pdf",
    summary="Startliste als PDF",
    description=STARTLIST_DESCRIPTION,
    response_class=Response,
    responses=PDF,
)
async def startlist_pdf(
    tournament_id: UUID,
    request: Request,
    session: SessionDep,
    _: Reader,
    competition_id: OptionalId = None,
    range_id: OptionalId = None,
    names: Names = "public",
    sort: StartlistSort = "competition",
) -> Response:
    meta, records = await _startlist(
        request, session, tournament_id, competition_id, range_id, names
    )
    return _pdf(tables.startlist_report(meta, records, sort), meta, "Startliste")


@router.get(
    "/startlist.csv",
    summary="Startliste als CSV",
    description=STARTLIST_DESCRIPTION + " UTF-8 mit BOM, Trennzeichen `;`.",
    response_class=Response,
    responses=CSV,
)
async def startlist_csv(
    tournament_id: UUID,
    request: Request,
    session: SessionDep,
    _: Reader,
    competition_id: OptionalId = None,
    range_id: OptionalId = None,
    names: Names = "public",
    sort: StartlistSort = "competition",
) -> Response:
    meta, records = await _startlist(
        request, session, tournament_id, competition_id, range_id, names
    )
    return _csv(tables.startlist_sheet(records, sort, meta.tz), meta, "Startliste")


# --- Ergebnisliste -------------------------------------------------------------------------

WINNERS_DESCRIPTION = (
    "Platzierungen aus der Rangliste (abgeschlossene Ergebnisse), je Wettbewerb und Klasse. "
    "Ohne `competition_id` alle Wettbewerbe mit Ergebnissen nacheinander. `top`: nur die "
    "ersten Plätze. `merged=true` legt Klassen zusammen. `include_provisional=false` lässt "
    "Ergebnisse in der Einspruchsfrist weg; sonst steht über dem Wettbewerb „vorläufig – "
    "Einspruchsfrist läuft bis …“. Ein Abbruch nach dem Kommando „Feuer“ wird nach dem bis "
    "dahin erzielten Ergebnis platziert (Sporthandbuch K 1.14 / L 1.12) und als „Abbruch (AB)“ "
    "gekennzeichnet. Ohne Platz bleiben nicht angetreten, disqualifiziert und Abbruch ohne "
    "Wertungswert (AB); ohne `top` stehen sie am Ende ihrer Klasse mit dem Grund und ohne "
    "Ergebnis, `include_aborted=false` lässt sie weg."
)


async def _winners(
    request: Request,
    session: SessionDep,
    tournament_id: UUID,
    *,
    competition_id: UUID | None,
    class_id: UUID | None,
    top: int | None,
    merged: bool,
    include_provisional: bool,
    names: NamesMode,
    include_aborted: bool = True,
) -> tuple[Meta, list[Any]]:
    await _check_names(request, names)
    sections = await service.winners(
        session,
        tournament_id,
        competition_id=competition_id,
        class_id=class_id,
        top=top,
        merged=merged,
        include_provisional=include_provisional,
        names=names,
        include_aborted=include_aborted,
    )
    return await service.meta(session, tournament_id, names), sections


@router.get(
    "/winners.pdf",
    summary="Ergebnisliste als PDF",
    description=WINNERS_DESCRIPTION,
    response_class=Response,
    responses=PDF,
)
async def winners_pdf(
    tournament_id: UUID,
    request: Request,
    session: SessionDep,
    _: Reader,
    competition_id: OptionalId = None,
    class_id: OptionalId = None,
    top: Top = None,
    merged: bool = False,
    include_provisional: bool = True,
    names: Names = "public",
    include_aborted: IncludeAborted = True,
) -> Response:
    meta, sections = await _winners(
        request,
        session,
        tournament_id,
        competition_id=competition_id,
        class_id=class_id,
        top=top,
        merged=merged,
        include_provisional=include_provisional,
        names=names,
        include_aborted=include_aborted,
    )
    return _pdf(tables.winners_report(meta, sections), meta, begriffe.RESULT_LIST_FILE)


@router.get(
    "/winners.csv",
    summary="Ergebnisliste als CSV",
    description=WINNERS_DESCRIPTION + " UTF-8 mit BOM, Trennzeichen `;`.",
    response_class=Response,
    responses=CSV,
)
async def winners_csv(
    tournament_id: UUID,
    request: Request,
    session: SessionDep,
    _: Reader,
    competition_id: OptionalId = None,
    class_id: OptionalId = None,
    top: Top = None,
    merged: bool = False,
    include_provisional: bool = True,
    names: Names = "public",
    include_aborted: IncludeAborted = True,
) -> Response:
    meta, sections = await _winners(
        request,
        session,
        tournament_id,
        competition_id=competition_id,
        class_id=class_id,
        top=top,
        merged=merged,
        include_provisional=include_provisional,
        names=names,
        include_aborted=include_aborted,
    )
    return _csv(tables.winners_sheet(sections, meta.tz), meta, begriffe.RESULT_LIST_FILE)


# --- Ergebnisse (Rohexport) ----------------------------------------------------------------


@router.get(
    "/results.csv",
    summary="Alle Ergebnisse als CSV (Rohexport)",
    description=(
        "Je Start eine Zeile: Startnummer, Person, Klasse, Wettbewerb, Versuch, Status, "
        "Ergebnis und die Teilwerte je Serie in festen Spalten „Serie <n> Ringe/Zeit/Zeit mit "
        "Zuschlag/Stehend“ (Serien über alle Abschnitte fortlaufend nummeriert; nur Spalten, "
        "die vorkommen). Zeiten in Sekunden mit Dezimalkomma. UTF-8 mit BOM, Trennzeichen `;`."
    ),
    response_class=Response,
    responses=CSV,
)
async def results_csv(
    tournament_id: UUID,
    request: Request,
    session: SessionDep,
    _: Reader,
    competition_id: OptionalId = None,
    names: Names = "public",
) -> Response:
    await _check_names(request, names)
    records = await service.results(
        session, tournament_id, competition_id=competition_id, names=names
    )
    meta = await service.meta(session, tournament_id, names)
    return _csv(tables.results_sheet(records, meta.tz), meta, "Ergebnisse")


__all__ = ["PERMISSION_FULL_NAMES", "PERMISSION_READ", "router"]
