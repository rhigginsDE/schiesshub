"""Daten der Listen, unabhängig vom Ausgabeformat.

`service.py` füllt sie aus den Sichten der Module `starts` und `ergebnisse`; `tables.py` macht
daraus Tabellen für CSV und PDF. Namen stehen hier schon so, wie die Liste sie zeigen darf
(`names=public`: nach Anzeige-Einstellung der Person; `names=full`: voller Name und Verein).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from app.core.localtime import DEFAULT_TIMEZONE, zone

NamesMode = Literal["public", "full"]
StartlistSort = Literal["start_number", "competition", "range"]
# Wie eine Zeile der Siegerliste gewertet ist (wie die Rangliste): regulär, hinten
# (unvollständig, nur live) oder ohne Platz (abgebrochen, unvollständig, prüfen).
# „aborted“ gibt es nicht mehr; der Wert bleibt für ältere Aufrufer erlaubt.
WinnerGroup = Literal["ranked", "last", "unranked", "aborted"]
# Wertungsmodelle, die Zeit von den Ringen abziehen: Listen zeigen dafür den Rechenweg.
TIME_MODELS = frozenset({"ringe_mit_zeitabzug", "ringe_minus_zeit"})


@dataclass(frozen=True, slots=True)
class Meta:
    tournament_name: str
    organizer: str | None
    date_from: date
    date_to: date
    generated_at: datetime
    names: NamesMode
    # Ortszeit des Turniers (`settings.timezone`) für alle Uhrzeiten der Liste.
    tz: ZoneInfo = field(default_factory=lambda: zone(DEFAULT_TIMEZONE))


@dataclass(frozen=True, slots=True)
class CompetitionInfo:
    id: uuid.UUID
    code: str | None
    name: str
    sort: int
    range_id: uuid.UUID | None
    range_name: str | None
    range_sort: int | None
    multi_start: bool
    planning: str
    # Abschnitte der Disziplin in Reihenfolge: (id, Name).
    sections: tuple[tuple[str, str], ...] = ()
    # Wertet der Wettbewerb Ringe? Ohne Ringe (reine Zeitwertung) keine Spalten für Zehner.
    rings: bool = True
    # Wertungsmodell der Definition („ringe_mit_zeitabzug“ …); None, wenn nicht lesbar.
    model: str | None = None
    # Sollzeit je Abschnitt in Sekunden (nur Abschnitte mit `sollzeit_s`): (id, Sekunden).
    target_times: tuple[tuple[str, Decimal], ...] = ()
    # `zeit_rundung` der Wertung („summe_abrunden“) oder None.
    time_rounding: str | None = None
    # Abweichungen vom Katalog als Text (`turnier.service.catalog_diff_of`); leer = keine.
    deviations: tuple[str, ...] = ()

    @property
    def time_model(self) -> bool:
        """Zieht die Wertung Zeit von den Ringen ab (Rechenweg in den Listen nötig)?"""
        return self.model in TIME_MODELS

    @property
    def title(self) -> str:
        """„4401 · Flinte 15 m Fallscheibe“ bzw. nur der Name ohne Kennziffer."""
        return f"{self.code} · {self.name}" if self.code else self.name


@dataclass(frozen=True, slots=True)
class PersonName:
    """Name und Verein, wie die Liste sie zeigt; `name=None` heißt: nur die Startnummer."""

    name: str | None
    club: str | None


@dataclass(frozen=True, slots=True)
class StartRecord:
    start_id: uuid.UUID
    entry_id: uuid.UUID
    start_number: int
    person: PersonName
    class_id: uuid.UUID
    class_short: str
    class_name: str
    competition: CompetitionInfo
    attempt: int
    status: str
    abort_reason: str | None
    queue_position: int | None
    heat_number: int | None
    heat_starts_at: datetime | None
    lane: int | None


@dataclass(frozen=True, slots=True)
class SeriesValue:
    section_id: str
    number: int
    struck: bool
    status: str
    rings: int | None
    time_cs: int | None
    standing: int | None
    total_cs: int | None


@dataclass(frozen=True, slots=True)
class TimedSection:
    """Ein Abschnitt mit Sollzeit (Mehrdistanz-Parcours): Zeit, Sollzeit, Abzug."""

    name: str
    time_cs: int | None
    target_s: Decimal
    deduction: Decimal | None
    # `min_teilergebnis` hat das Teilergebnis angehoben (Abzug wirkt nicht voll).
    floored: bool
    result: Decimal


@dataclass(frozen=True, slots=True)
class TimeScore:
    """Rechenweg einer Wertung mit Zeit (`TIME_MODELS`), aus der Wertung des Servers.

    - `ringe_mit_zeitabzug`: `time_cs` ist die Gesamtzeit der Abschnitte mit Sollzeit,
      `deduction` der Ringabzug; `sections` je Abschnitt mit Sollzeit.
    - `ringe_minus_zeit`: `time_cs` ist die Summe der Serienzeiten, `deduction` der Abzug
      (Ringe − Ergebnis; mit `rounded` vorher auf volle Sekunden abgerundet).
    """

    model: str
    rings: int | None
    time_cs: int | None
    # Sollzeit, wenn es genau einen Abschnitt mit Sollzeit gibt.
    target_s: Decimal | None
    deduction: Decimal | None
    sections: tuple[TimedSection, ...] = ()
    rounded: bool = False


@dataclass(frozen=True, slots=True)
class WinnerRow:
    place: int | None
    tied: bool
    tie_unresolved: bool
    group: WinnerGroup
    entry_id: uuid.UUID
    start_number: int
    attempt: int
    person: PersonName
    class_id: uuid.UUID
    class_short: str
    score: Decimal | None
    complete: bool
    tens: int | None
    inner_tens: int | None
    series: tuple[SeriesValue, ...]
    # final, provisional, running, aborted, review (wie die Rangliste)
    status: str
    abort_reason: str | None
    provisional_until: datetime | None
    # Rechenweg bei Wertung mit Zeit; None bei anderen Modellen oder ohne Ergebnis.
    time_score: TimeScore | None = None


@dataclass(frozen=True, slots=True)
class WinnerTable:
    """Eine Wertungsgruppe: eine Klasse (mit `merged` auch zusammengelegte) oder gemeinsam."""

    class_id: uuid.UUID | None
    title: str
    rows: tuple[WinnerRow, ...]
    # Mehr als eine Klasse in der Gruppe: Spalte „Klasse“ nötig.
    mixed_classes: bool


@dataclass(frozen=True, slots=True)
class WinnerSection:
    competition: CompetitionInfo
    unit: str | None
    tables: tuple[WinnerTable, ...]
    # Spätestes Ende der Einspruchsfrist unter den vorläufigen Zeilen; None ohne vorläufige.
    provisional_until: datetime | None


@dataclass(frozen=True, slots=True)
class ResultRecord:
    start: StartRecord
    has_result: bool
    score: Decimal | None
    unit: str | None
    complete: bool
    tens: int | None
    inner_tens: int | None
    finalized_at: datetime | None
    provisional_until: datetime | None
    is_provisional: bool
    needs_review: bool
    series: tuple[SeriesValue, ...] = field(default_factory=tuple)
    time_score: TimeScore | None = None
