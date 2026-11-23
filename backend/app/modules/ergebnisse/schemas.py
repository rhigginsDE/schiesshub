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

from app.core.errors import FieldError
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
    # Optional: Stand, den der Mensch gesehen hat. Weicht der Server davon ab (andere
    # Sequenznummer oder anderes Ergebnis), wird nicht abgeschlossen (409 mit aktuellem Stand).
    expected_seq: Seq | None = None
    # Als Zahl oder Text („40.00“) wie `score` in den Antworten.
    expected_score: Annotated[Decimal, Field(strict=False)] | None = None


class ReopenRequest(StrictModel):
    reason: Reason
    base_seq: Seq | None = None


class CorrectRequest(StrictModel):
    raw: dict[str, Any]
    reason: Reason
    base_seq: Seq


class PreviewRequest(StrictModel):
    # Rohwerte wie bei `PUT …/raw` bzw. `POST …/correct`; nichts wird gespeichert.
    raw: dict[str, Any]


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


class PreviewOut(BaseModel):
    """Probe-Rechnung von Rohwerten gegen die aktuelle Definition; nichts ist gespeichert."""

    start_id: UUID
    status: StartStatus
    # Aktuelle Sequenznummer des Starts (als `base_seq` für das Speichern).
    seq: int
    definition_revision: int
    # Keine Fehler für einen Zwischenstand (`PUT …/raw` würde angenommen).
    valid: bool
    errors: list[FieldError]
    # Vollständig: Abschließen bzw. Korrigieren würde angenommen.
    complete: bool
    # Was zum Abschließen/Korrigieren noch fehlt oder nicht passt (Pfad und Meldung).
    finalize_errors: list[FieldError]
    # Wertung mit Rechenweg; null, solange `errors` nicht leer ist.
    computed: ComputedResult | None
    score: Decimal | None


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
    # Kennziffer aus dem Katalog (z. B. „1.10“); null bei eigenem Wettbewerb.
    competition_code: str | None
    # Stand des Wettbewerbs; null, solange er keinem Stand zugeordnet ist.
    range_id: UUID | None
    range_name: str | None
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
    # Bei Zehntelwertung Text mit einer Nachkommastelle („20.1“), sonst ganze Zahl.
    rings: Decimal | int | None
    time_cs: int | None
    standing: int | None
    total_cs: int | None


class RankingRow(BaseModel):
    place: int | None
    tied: bool
    # Geteilt und nicht entschieden (Grund in `tie_reason`, Text in `tie_note`).
    tie_unresolved: bool
    # missing_data: Rohdaten für `tie_criterion` fehlen; manual: `tie_criterion` rechnet der
    # Server nicht (nach Sportordnung entscheiden); shootoff: Stechen (`stechen_bis_platz`).
    tie_reason: Literal["missing_data", "manual", "shootoff"] | None = None
    tie_criterion: str | None = None
    needs_shootoff: bool = False
    # Hinweis zum Anzeigen, z. B. „Ringgleichheit auf Platz 2: Stechen“.
    tie_note: str | None = None
    # ranked: regulär; last: unvollständig (live), hinten; unranked: ohne Platz (abgebrochen,
    # unvollständig in einer endgültigen Liste, prüfen).
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
    # Kennziffer aus dem Katalog („4401“); null bei eigenen Wettbewerben.
    competition_code: str | None = None
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
    # Alle Starts (auch abgebrochene).
    starts_total: int
    # Abgeschlossen (auch in der Einspruchsfrist).
    starts_final: int
    # Laufend: aufgerufen, erfasst oder angemeldet mit Zwischenstand.
    starts_running: int
    # Wartend: angemeldet ohne Zwischenstand. Abgebrochene zählen nur in `starts_total`.
    starts_waiting: int
    needs_review: int
    provisional: int
    # Führende je Wertungsgruppe (Platz 1, bei Gleichstand mehrere), aus der Rangliste
    # `scope=final` mit vorläufigen Ergebnissen.
    leaders: list[LeaderOut]


class RankingSummaryOut(BaseModel):
    tournament_id: UUID
    generated_at: datetime
    competitions: list[CompetitionSummary]
