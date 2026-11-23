"""Ergebnis einer Wertung (`result_current.computed`).

Alle Modelle lassen sich mit `model_dump(mode="json")` als JSON speichern und mit
`ComputedResult.model_validate(...)` wieder einlesen; `Decimal` wird dabei zu Text („187“, „75.20“).
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.scoring.errors import Issue
from app.scoring.spec import Direction
from app.scoring.status import SeriesStatus


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class SeriesResult(_Frozen):
    number: int
    struck: bool
    """Gestrichen (`serien_gewertet`): Werte nur zur Anzeige, nicht in Summen und Rangfolge."""
    status: SeriesStatus
    """Ablauf der Serie (siehe `app.scoring.status`)."""
    captured: bool
    complete: bool
    shots_entered: int
    shots_expected: int
    rings: Decimal | int | None
    """Ringe der Serie (bei unvollständiger Serie die bisher erfassten); None ohne Ringe.
    Bei Zehntelwertung `Decimal` mit einer Nachkommastelle (JSON: Text „30.7“)."""
    tens: int | None
    """Zehner einschließlich Innenzehner; None, wenn als Summe ohne Zehner erfasst."""
    inner_tens: int | None
    measured_time_cs: int | None
    """Erfasste Zeit, wie eingegeben."""
    time_cs: int | None
    """Gewertete Zeit: bei Abbruch/Störung `zeit_bei_abbruch_s`, sonst die erfasste."""
    standing: int | None
    penalty_cs: int | None
    """Zuschlag für stehende Scheiben bzw. bei Störung vor dem ersten Schuss."""
    total_cs: int | None
    """Zeit plus Zuschlag (nur Abschnitte mit Zeit je Serie)."""
    shot_values: list[Decimal | int] | None = None
    """Zählwerte der erfassten Schüsse in Reihenfolge („X“ als 10); None bei Seriensumme."""


class SectionResult(_Frozen):
    id: str
    name: str
    complete: bool
    rings: Decimal | int | None
    time_cs: int | None
    """Summe der Serienzeiten bzw. Gesamtzeit des Abschnitts."""
    penalty_cs: int | None
    overtime_s: int | None
    """Volle Sekunden über der Sollzeit."""
    deduction: Decimal | None
    """Ringabzug für die Zeit über der Sollzeit."""
    subtotal: Decimal
    """Teilergebnis vor einer Untergrenze."""
    result: Decimal
    """Teilergebnis, das in die Summe eingeht."""
    floored: bool
    """True, wenn `min_teilergebnis` das Teilergebnis angehoben hat."""
    series: list[SeriesResult]
    """Alle Serien, auch gestrichene (`struck`)."""


class Progress(_Frozen):
    shots_entered: int
    shots_expected: int
    series_complete: int
    series_expected: int
    section_times_entered: int
    section_times_expected: int


class ComputedResult(_Frozen):
    model: str
    direction: Direction
    unit: str
    score: Decimal
    score_text: str
    complete: bool
    rings: Decimal | int | None
    tens: int | None
    """Zehner einschließlich Innenzehner; bei Zehntelwertung alle Schüsse ab 10,0."""
    inner_tens: int | None
    """Innenzehner („X“); bei Zehntelwertung immer None (keine Eingabe dafür)."""
    ring_counts: dict[int, int] | None
    """Anzahl Schüsse je ganzem Ring 0–10 (Innenzehner als 10, 9,8 als 9), dazu höhere Werte aus
    `ringwerte` (Bogen 3D: 11); None, sobald eine Serie nur als Summe vorliegt."""
    time_cs: int | None
    penalty_cs: int | None
    deduction: Decimal | None
    parcours_time_cs: int | None
    """Summe der Gesamtzeiten der Abschnitte mit Sollzeit/Abbruchzeit; None, solange eine fehlt."""
    tie_breakers_missing: list[str]
    """Gleichstandskriterien der Definition ohne Angaben (z. B. Seriensumme ohne Zehner)."""
    sections: list[SectionResult]
    progress: Progress
    steps: list[str]
    warnings: list[Issue]
    decimals: int = 0
    """Nachkommastellen der Ringwerte: 1 bei Zehntelwertung, sonst 0."""
    hits: int | None = None
    """Treffer (Schüsse mit Wert über 0); None, sobald eine Serie nur als Summe vorliegt."""
