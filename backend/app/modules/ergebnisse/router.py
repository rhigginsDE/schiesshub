"""HTTP-Schnittstelle des Moduls `ergebnisse`: Erfassung, Verlauf, Neuaufbau, Ranglisten.

Schreibende Vorgänge nehmen einen optionalen Header `Idempotency-Key` an: Derselbe Schlüssel mit
demselben Inhalt liefert den aktuellen Stand, ohne ein zweites Ereignis zu schreiben (für
Wiederholungen nach einem Verbindungsabbruch). `base_seq` ist die letzte dem Client bekannte
Sequenznummer; weicht sie ab, antwortet der Server mit 409 und dem aktuellen Stand.
"""

from collections.abc import Awaitable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.db import SessionDep
from app.core.events import EventHubDep
from app.core.security import Actor, require
from app.modules.ergebnisse import ranking, service, views
from app.modules.ergebnisse.recompute import recompute_competition
from app.modules.ergebnisse.schemas import (
    AbortResultRequest,
    CaptureMode,
    CorrectRequest,
    EventOut,
    FinalizeRequest,
    FormOut,
    PreviewOut,
    PreviewRequest,
    RankingOut,
    RankingSummaryOut,
    RawPut,
    RecomputeOut,
    ReopenRequest,
    ResultState,
    ReviewItemOut,
    SeqConflictOut,
)
from app.modules.ergebnisse.service import SeqConflict

PERMISSION_READ = "result.read"
PERMISSION_CAPTURE = "result.capture"
PERMISSION_CORRECT = "result.correct"

Reader = Annotated[Actor, Depends(require(PERMISSION_READ))]
Capturer = Annotated[Actor, Depends(require(PERMISSION_CAPTURE))]
Corrector = Annotated[Actor, Depends(require(PERMISSION_CORRECT))]
IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=100,
        description="Beliebiger eindeutiger Schlüssel je Vorgang, z. B. eine UUID des Clients.",
    ),
]

router = APIRouter(prefix="/tournaments/{tournament_id}", tags=["ergebnisse"])

START = "/starts/{start_id}"
NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Nicht gefunden"}}
WRITE = {
    **NOT_FOUND,
    status.HTTP_409_CONFLICT: {
        "description": (
            "Im aktuellen Zustand nicht möglich. Bei veraltetem `base_seq` mit dem aktuellen "
            "Stand in `current`."
        ),
        "model": SeqConflictOut,
    },
}


async def _write(operation: Awaitable[ResultState]) -> ResultState | JSONResponse:
    try:
        return await operation
    except SeqConflict as conflict:
        body = SeqConflictOut(detail=str(conflict), current=conflict.state)
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=jsonable_encoder(body))


async def _may_capture(request: Request) -> bool:
    """Ob der Anfragende erfassen darf (dann zeigt die Maske den vollen Namen)."""
    try:
        await require(PERMISSION_CAPTURE)(request)
    except HTTPException:
        return False
    return True


# --- Erfassung -------------------------------------------------------------------


@router.get(
    f"{START}/form",
    summary="Eingabemaske eines Starts",
    description=(
        "Maske für die aktuelle Definition des Wettbewerbs, Kopf des Starts (mit "
        "`result.capture` voller Name, sonst nach Anzeige-Einstellung; dazu Kennziffer des "
        "Wettbewerbs und Stand), aktueller Rohwert und "
        "Zwischenstand. `capture_mode` wählt nur die Darstellung (Einzelschuss oder "
        "Seriensumme); ohne Angabe gilt die des Wettbewerbs. Rohwerte dürfen beides enthalten "
        "und werden gleich gewertet."
    ),
    responses=WRITE,
)
async def get_form(
    tournament_id: UUID,
    start_id: UUID,
    request: Request,
    session: SessionDep,
    _: Reader,
    capture_mode: CaptureMode | None = None,
) -> FormOut:
    return await views.form(
        session,
        tournament_id,
        start_id,
        capture_mode=capture_mode,
        full_name=await _may_capture(request),
    )


@router.put(
    f"{START}/raw",
    summary="Rohwerte erfassen",
    description=(
        "Ersetzt den Rohwert-Stand eines offenen Starts (Zwischenstand erlaubt). Der Start wird "
        "dabei „erfasst“, auch ohne vorheriges Aufrufen (die Bahn bleibt dann leer). Antwort: "
        "neuer Stand mit Wertung und Rechenweg. Fehlerhafte Rohwerte: 422 mit Pfad und Meldung "
        "je Fehler."
    ),
    responses=WRITE,
)
async def put_raw(
    tournament_id: UUID,
    start_id: UUID,
    data: RawPut,
    session: SessionDep,
    events: EventHubDep,
    actor: Capturer,
    idempotency_key: IdempotencyKey = None,
) -> ResultState:
    return await _write(
        service.set_raw(
            session,
            events,
            actor,
            tournament_id,
            start_id,
            data.raw,
            data.base_seq,
            idempotency_key,
        )
    )


@router.post(
    f"{START}/preview",
    summary="Rohwerte probeweise werten (ohne Speichern)",
    description=(
        "Rechnet `raw` gegen die aktuelle Definition des Wettbewerbs durch und liefert "
        "Validierungsfehler und berechneten Stand, speichert aber nichts (kein Ereignis, kein "
        "Statuswechsel). `errors`: Fehler, die auch `PUT …/raw` meldete; `finalize_errors`: was "
        "zum Abschließen oder Korrigieren fehlt. Für „Korrigieren“ und Eingaben, die erst "
        "später gespeichert werden."
    ),
    responses=WRITE,
)
async def preview(
    tournament_id: UUID,
    start_id: UUID,
    data: PreviewRequest,
    session: SessionDep,
    _: Reader,
) -> PreviewOut:
    return await service.preview(session, tournament_id, start_id, data.raw)


@router.post(
    f"{START}/finalize",
    summary="Ergebnis abschließen",
    description=(
        "Verlangt vollständige Rohwerte (sonst 422 mit der Liste). Der Start wird "
        "„abgeschlossen“; bis `provisional_until` (Einspruchsfrist des Turniers) gilt das "
        "Ergebnis als vorläufig. Optional `expected_seq` und `expected_score`: der Stand, den "
        "der Mensch bestätigt hat; weicht der Server ab, 409 mit dem aktuellen Stand (nichts "
        "wird abgeschlossen)."
    ),
    responses=WRITE,
)
async def finalize(
    tournament_id: UUID,
    start_id: UUID,
    data: FinalizeRequest,
    session: SessionDep,
    events: EventHubDep,
    actor: Capturer,
    idempotency_key: IdempotencyKey = None,
) -> ResultState:
    return await _write(
        service.finalize(
            session,
            events,
            actor,
            tournament_id,
            start_id,
            data.base_seq,
            idempotency_key,
            expected_seq=data.expected_seq,
            expected_score=data.expected_score,
        )
    )


@router.post(
    f"{START}/reopen",
    summary="Abschluss zurücknehmen (mit Grund)",
    responses=WRITE,
)
async def reopen(
    tournament_id: UUID,
    start_id: UUID,
    data: ReopenRequest,
    session: SessionDep,
    events: EventHubDep,
    actor: Corrector,
    idempotency_key: IdempotencyKey = None,
) -> ResultState:
    return await _write(
        service.reopen(
            session,
            events,
            actor,
            tournament_id,
            start_id,
            data.reason,
            data.base_seq,
            idempotency_key,
        )
    )


@router.post(
    f"{START}/correct",
    summary="Abgeschlossenes Ergebnis korrigieren (mit Grund)",
    description=(
        "Ersetzt die Rohwerte eines abgeschlossenen Ergebnisses; es bleibt abgeschlossen. Die "
        "Einspruchsfrist beginnt neu, außer das Turnier hat "
        "`settings.protest_restart_on_correction: false` (dann läuft sie ab dem Abschluss "
        "weiter)."
    ),
    responses=WRITE,
)
async def correct(
    tournament_id: UUID,
    start_id: UUID,
    data: CorrectRequest,
    session: SessionDep,
    events: EventHubDep,
    actor: Corrector,
    idempotency_key: IdempotencyKey = None,
) -> ResultState:
    return await _write(
        service.correct(
            session,
            events,
            actor,
            tournament_id,
            start_id,
            data.raw,
            data.reason,
            data.base_seq,
            idempotency_key,
        )
    )


@router.post(
    f"{START}/result/abort",
    summary="Start mit Ergebnis-Ereignis abbrechen (dns, dnf, dsq)",
    description=(
        "Schreibt das Ereignis `aborted` (mit optionalem Grund) ins Ergebnisprotokoll und "
        "wechselt den Status. `POST …/starts/{start_id}/abort` des Moduls `starts` führt zum "
        "selben Ergebnis (ohne Grund, Antwort ist dort der Start). Vorhandene Rohwerte bleiben "
        "erhalten."
    ),
    responses=WRITE,
)
async def abort(
    tournament_id: UUID,
    start_id: UUID,
    data: AbortResultRequest,
    session: SessionDep,
    events: EventHubDep,
    actor: Capturer,
    idempotency_key: IdempotencyKey = None,
) -> ResultState:
    return await _write(
        service.abort(
            session,
            events,
            actor,
            tournament_id,
            start_id,
            data.abort_reason,
            data.reason,
            idempotency_key,
        )
    )


@router.get(
    f"{START}/events",
    summary="Verlauf eines Ergebnisses",
    description=(
        "Alle Ereignisse: wer, wann, was, Grund und Unterschied zum vorigen Rohwert. "
        "`user_name` und `device_name` werden zum Abfragezeitpunkt aufgelöst (heutiger Name); "
        "`user_name` ist null, wenn beim Ereignis niemand angemeldet war oder die Person "
        "gelöscht ist."
    ),
    responses=NOT_FOUND,
)
async def list_events(
    tournament_id: UUID, start_id: UUID, session: SessionDep, _: Reader
) -> list[EventOut]:
    return await views.event_list(session, tournament_id, start_id)


# --- Neuaufbau und Prüfliste ------------------------------------------------------------


@router.post(
    "/competitions/{competition_id}/recompute",
    summary="Ergebnisse eines Wettbewerbs neu berechnen",
    description=(
        "Baut den aktuellen Stand aller Starts aus den Ereignissen und der aktuellen Definition "
        "neu auf. Läuft bei jeder Änderung der Wertung automatisch."
    ),
    responses=NOT_FOUND,
)
async def recompute(
    tournament_id: UUID,
    competition_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: Corrector,
) -> RecomputeOut:
    await service.competition_of(session, tournament_id, competition_id)
    result = await recompute_competition(session, competition_id, actor)
    await session.commit()
    events.publish(
        service.EVENT_RECOMPUTED,
        {"tournament_id": str(tournament_id), "competition_id": str(competition_id)},
    )
    return RecomputeOut(
        competition_id=result.competition_id,
        definition_revision=result.definition_revision,
        recomputed=result.recomputed,
        needs_review=result.needs_review,
    )


@router.get(
    "/results/needs-review",
    summary="Zu prüfende Ergebnisse",
    description=(
        "Ergebnisse, die nach einer Änderung der Wertung unvollständig oder nicht wertbar sind."
    ),
    responses=NOT_FOUND,
)
async def needs_review(tournament_id: UUID, session: SessionDep, _: Reader) -> list[ReviewItemOut]:
    return await views.review_list(session, tournament_id)


# --- Ranglisten ----------------------------------------------------------------------


@router.get(
    "/competitions/{competition_id}/ranking",
    summary="Rangliste eines Wettbewerbs",
    description=(
        "Platzierungen je Klasse (bei gemeinsamer Wertung eine Gruppe). `scope=live` nimmt "
        "laufende Zwischenstände auf (`status: running`). `merged=true` legt Klassen über "
        "`merge_into_id` zusammen. Namen nur nach Anzeige-Einstellung der Person. "
        "Ein Abbruch nach dem Kommando „Feuer“ (aufgegeben mit erfassten Werten) wird nach dem "
        "bis dahin erzielten Ergebnis platziert (Sporthandbuch K 1.14 / L 1.12; nicht "
        "geschossene Serien nach der Regel der Wertung; `abort_label`: „Abbruch (AB)“). Ohne "
        "Platz bleiben nicht angetreten, disqualifiziert, Abbruch ohne Wertungswert und "
        "Abbrüche ohne vergleichbares Ergebnis (`abort_note`): Sie stehen am Ende ihrer Gruppe "
        "(`group: unranked`, `abort_reason`); `include_aborted=false` lässt sie weg. "
        "In `scope=final` stehen auch unvollständige "
        "Ergebnisse ohne Platz da."
    ),
    responses=NOT_FOUND,
)
async def get_ranking(
    tournament_id: UUID,
    competition_id: UUID,
    session: SessionDep,
    _: Reader,
    class_id: UUID | None = None,
    include_provisional: bool = True,
    scope: Annotated[ranking.Scope, Query()] = "final",
    merged: bool = False,
    include_aborted: bool = True,
) -> RankingOut:
    return await ranking.competition_ranking(
        session,
        tournament_id,
        competition_id,
        class_id=class_id,
        include_provisional=include_provisional,
        scope=scope,
        merged=merged,
        include_aborted=include_aborted,
    )


@router.get(
    "/ranking-summary",
    summary="Stand aller Wettbewerbe",
    description="Je Wettbewerb: Starts je Status, zu prüfende, vorläufige und die Führenden.",
    responses=NOT_FOUND,
)
async def get_ranking_summary(
    tournament_id: UUID, session: SessionDep, _: Reader
) -> RankingSummaryOut:
    return await ranking.ranking_summary(session, tournament_id)
