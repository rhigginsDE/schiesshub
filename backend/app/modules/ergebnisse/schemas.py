"""Ein- und Ausgabeformate des Moduls `ergebnisse`. Feldnamen englisch wie im Datenmodell.

Eingaben sind streng: unbekannte Felder sind Fehler. Rohwerte (`raw`) prüft die Wertung
(`app.scoring.validate_raw`) und meldet jeden Fehler mit Pfad, zum Beispiel
`raw.sections.fallscheibe.series[2].standing`.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.modules.starts.rules import AbortReason, StartStatus
from app.modules.turnier.schemas import StrictModel
from app.scoring import ComputedResult, FormDescription

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Seq = Annotated[int, Field(ge=0)]
EventType = Literal["raw_set", "finalized", "corrected", "reopened", "aborted"]
CaptureMode = Literal["shot", "series"]
# Stand eines Ergebnisses in Ranglisten: vorläufig (Einspruchsfrist läuft), endgültig, läuft
# (nur `scope=live`), abgebrochen, prüfen (nach Änderung der Wertung nicht wertbar).
RowStatus = Literal["provisional", "final", "running", "aborted", "review"]


# --- Eingaben ------------------------------------------------------------------


class RawPut(StrictModel):
    # Vollständiger Rohwert-Stand des Starts (ersetzt den vorigen), Format: docs/DATENMODELL.md.
    raw: dict[str, Any]
    # Letzte dem Client bekannte Sequenznummer (`seq` der letzten Antwort, 0 ohne Ereignis).
    base_seq: Seq


class FinalizeRequest(StrictModel):
    base_seq: Seq


class ReopenRequest(StrictModel):
    reason: Reason
    base_seq: Seq | None = None


class CorrectRequest(StrictModel):
    raw: dict[str, Any]
    reason: Reason
    base_seq: Seq


class AbortResultRequest(StrictModel):
    abort_reason: AbortReason
    reason: Reason | None = None


# --- Stand eines Starts --------------------------------------------------------------


class ResultState(BaseModel):
    """Aktueller Stand eines Starts mit Wertung und Rechenweg (`computed.steps`)."""

    start_id: UUID
    status: StartStatus
    abort_reason: AbortReason | None
    # Sequenznummer des letzten Ereignisses; als `base_seq` der nächsten Eingabe mitschicken.
    seq: int
    raw: dict[str, Any]
    computed: ComputedResult | None
    score: Decimal | None
    is_final: bool
    finalized_at: datetime | None
    provisional_until: datetime | None
    is_provisional: bool
    needs_review: bool
    review_reason: str | None
    definition_revision: int


class SeqConflictOut(BaseModel):
    """HTTP 409: Ein anderes Gerät hat inzwischen erfasst. Nichts wurde geschrieben."""

    detail: str
    current: ResultState


# --- Eingabemaske ------------------------------------------------------------------


class FormHeader(BaseModel):
    start_number: int
    # Nach Anzeige-Einstellung der Person; mit `result.capture` immer der volle Name.
    display_name: str | None
    full_name_shown: bool
    club: str | None
    class_id: UUID
    class_name: str
    class_short: str
    competition_id: UUID
    competition_name: str
    attempt: int
    # Gebuchte Starts der Person in diesem Wettbewerb („Versuch 2 von 3“).
    attempts_booked: int
    max_starts: int
    lane: int | None


class FormOut(BaseModel):
    header: FormHeader
    # Erfassungsart des Wettbewerbs; `form.capture_mode` ist die tatsächlich gezeigte.
    competition_capture_mode: CaptureMode
    form: FormDescription
    current: ResultState


# --- Verlauf -------------------------------------------------------------------


class RawChangeOut(BaseModel):
    path: str
    before: Any
    after: Any


class EventOut(BaseModel):
    seq: int
    type: EventType
    type_label: str
    created_at: datetime
    user_id: UUID | None
    user_name: str | None
    device_id: UUID | None
    device_name: str | None
    reason: str | None
    abort_reason: AbortReason | None
    provisional_until: datetime | None
    # Nur bei raw_set und corrected: neuer Rohwert und Unterschied zum vorigen.
    raw: dict[str, Any] | None
    changes: list[RawChangeOut]


# --- Neuaufbau -----------------------------------------------------------------


class RecomputeOut(BaseModel):
    competition_id: UUID
    definition_revision: int
    recomputed: int
    needs_review: int


class ReviewItemOut(BaseModel):
    start_id: UUID
    competition_id: UUID
    competition_name: str
    start_number: int
    display_name: str | None
    attempt: int
    status: StartStatus
    review_reason: str
    definition_revision: int


# --- Ranglisten ------------------------------------------------------------------


class SeriesPart(BaseModel):
    section_id: str
    number: int
    struck: bool
    status: str
    rings: int | None
    time_cs: int | None
    standing: int | None
    total_cs: int | None


class RankingRow(BaseModel):
    place: int | None
    tied: bool
    tie_unresolved: bool
    # ranked: regulär; last: unvollständig oder aufgegeben, hinten; unranked: ohne Platz.
    group: Literal["ranked", "last", "unranked"]
    start_id: UUID
    entry_id: UUID
    start_number: int
    attempt: int
    # Nach `display_mode`: voll, abgekürzt oder null (dann nur die Startnummer zeigen).
    display_name: str | None
    # Nur mit `show_club`.
    club: str | None
    class_id: UUID
    class_short: str
    score: Decimal | None
    score_text: str | None
    complete: bool
    tens: int | None
    inner_tens: int | None
    series: list[SeriesPart]
    status: RowStatus
    abort_reason: AbortReason | None
    provisional_until: datetime | None


class RankingGroup(BaseModel):
    # Klasse der Wertung; null bei gemeinsamer Wertung (`combined_ranking`).
    class_id: UUID | None
    class_name: str | None
    class_short: str | None
    # Klassen, die hier gewertet werden (mit `merged=true` auch die zusammengelegten).
    class_ids: list[UUID]
    rows: list[RankingRow]


class RankingOut(BaseModel):
    competition_id: UUID
    competition_name: str
    scope: Literal["final", "live"]
    include_provisional: bool
    merged: bool
    combined: bool
    multi_start_rule: Literal["best", "first", "all"]
    direction: str | None
    unit: str | None
    generated_at: datetime
    groups: list[RankingGroup]


class StatusCounts(BaseModel):
    registered: int = 0
    called: int = 0
    captured: int = 0
    final: int = 0
    aborted: int = 0


class LeaderOut(BaseModel):
    class_id: UUID | None
    class_short: str | None
    start_number: int
    display_name: str | None
    club: str | None
    score_text: str | None
    status: RowStatus


class CompetitionSummary(BaseModel):
    competition_id: UUID
    competition_name: str
    counts: StatusCounts
    needs_review: int
    provisional: int
    # Führende je Wertungsgruppe (Platz 1, bei Gleichstand mehrere), aus der Rangliste
    # `scope=final` mit vorläufigen Ergebnissen.
    leaders: list[LeaderOut]


class RankingSummaryOut(BaseModel):
    tournament_id: UUID
    generated_at: datetime
    competitions: list[CompetitionSummary]
