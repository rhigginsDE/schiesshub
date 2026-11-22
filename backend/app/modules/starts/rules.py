"""Reine Regeln des Moduls `starts`: ohne Datenbank, einzeln getestet.

Statusmaschine, Startgeld, Mehrfachstart, Startnummern, Reihenfolge, Durchgangsserien und die
Bahnvergabe beim „nächste aufrufen“.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

StartStatus = Literal["registered", "called", "captured", "final", "aborted"]
AbortReason = Literal["dns", "dnf", "dsq"]

START_STATUSES: tuple[StartStatus, ...] = ("registered", "called", "captured", "final", "aborted")
ABORT_REASONS: tuple[AbortReason, ...] = ("dns", "dnf", "dsq")

STATUS_LABELS: dict[str, str] = {
    "registered": "angemeldet",
    "called": "aufgerufen",
    "captured": "erfasst",
    "final": "abgeschlossen",
    "aborted": "abgebrochen",
}

# Erlaubte Übergänge. `called → registered` ist „zurückstellen“, `final → captured` das
# Wiederöffnen eines abgeschlossenen Ergebnisses durch das Ergebnis-Modul (mit Grund).
# `registered → captured` ist die nachträgliche Erfassung ohne Aufrufen (kleine Vereine rufen
# nicht auf); bei der Reihenfolge bleibt die Bahn dann leer.
TRANSITIONS: Mapping[StartStatus, frozenset[StartStatus]] = {
    "registered": frozenset({"called", "captured", "aborted"}),
    "called": frozenset({"registered", "captured", "aborted"}),
    "captured": frozenset({"final", "aborted"}),
    "final": frozenset({"captured"}),
    "aborted": frozenset(),
}
REASON_REQUIRED: frozenset[tuple[StartStatus, StartStatus]] = frozenset({("final", "captured")})

# Ab hier hat ein Start eine Bahn belegt oder ein Ergebnis; eine Anmeldung damit bleibt stehen.
SHOT_STATUSES: frozenset[StartStatus] = frozenset({"called", "captured", "final"})

# Schlüssel in `tournament.settings` (Modul `turnier`): erste automatisch vergebene Startnummer.
# Fehlt er (ältere Turniere), gilt der Standard.
START_NUMBER_SETTING = "first_start_number"
DEFAULT_START_NUMBER_FROM = 1


class RuleError(ValueError):
    """Eine Regel ist verletzt. Die Meldung ist für Anwender gedacht."""


# --- Statusmaschine ----------------------------------------------------------


def check_transition(
    current: StartStatus,
    to: StartStatus,
    *,
    abort_reason: AbortReason | None = None,
    reason: str | None = None,
) -> None:
    """Prüft einen Statuswechsel; wirft `RuleError` mit verständlicher Meldung."""
    if to not in TRANSITIONS[current]:
        raise RuleError(
            f"Ein Start im Status „{STATUS_LABELS[current]}“ kann nicht "
            f"„{STATUS_LABELS[to]}“ werden."
        )
    if to == "aborted" and abort_reason is None:
        raise RuleError(
            "Für den Abbruch wird ein Grund benötigt: dns (nicht angetreten), "
            "dnf (aufgegeben) oder dsq (disqualifiziert)."
        )
    if to != "aborted" and abort_reason is not None:
        raise RuleError("Ein Abbruchgrund gehört nur zum Abbrechen eines Starts.")
    if (current, to) in REASON_REQUIRED and not (reason and reason.strip()):
        raise RuleError("Zum Wiederöffnen eines abgeschlossenen Starts wird ein Grund benötigt.")


def has_result(status: str, abort_reason: str | None) -> bool:
    """Ob ein Start schon geschossen wurde (oder gerade auf der Bahn steht)."""
    if status in SHOT_STATUSES:
        return True
    return status == "aborted" and abort_reason in ("dnf", "dsq")


# --- Startgeld und Mehrfachstart ---------------------------------------------


def start_fee(attempt: int, fee_first_cents: int, fee_repeat_cents: int) -> int:
    """Betrag für den `attempt`-ten Start einer Person in einem Wettbewerb (ab 1)."""
    if attempt < 1:
        raise ValueError("attempt beginnt bei 1")
    return fee_first_cents if attempt == 1 else fee_repeat_cents


def check_start_limit(multi_start: bool, max_starts: int, booked: int, count: int) -> None:
    """Prüft, ob `count` weitere Starts zu `booked` vorhandenen passen."""
    limit = max_starts if multi_start else 1
    if booked + count <= limit:
        return
    if limit == 1:
        raise RuleError("In diesem Wettbewerb ist nur ein Start je Person möglich.")
    raise RuleError(
        f"In diesem Wettbewerb sind höchstens {limit} Starts je Person möglich; "
        f"gebucht {'ist' if booked == 1 else 'sind'} schon {booked}."
    )


# --- Startnummern ------------------------------------------------------------


def first_start_number(settings: Mapping[str, Any]) -> int:
    value = settings.get(START_NUMBER_SETTING, DEFAULT_START_NUMBER_FROM)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return DEFAULT_START_NUMBER_FROM
    return value


def next_free_number(used: Iterable[int], start_from: int) -> int:
    """Kleinste freie Startnummer ab `start_from`."""
    taken = set(used)
    number = start_from
    while number in taken:
        number += 1
    return number


# --- Reihenfolge -------------------------------------------------------------


def move_to(order: Sequence[UUID], item: UUID, position: int) -> list[UUID]:
    """Setzt `item` an `position` (ab 1) der Reihenfolge."""
    if item not in order:
        raise RuleError("Der Start wartet nicht in dieser Reihenfolge.")
    if not 1 <= position <= len(order):
        raise RuleError(f"Die Position muss zwischen 1 und {len(order)} liegen.")
    rest = [other for other in order if other != item]
    rest.insert(position - 1, item)
    return rest


@dataclass(frozen=True, slots=True)
class Waiting:
    start_id: UUID
    # Anmeldung, also die Person im Turnier.
    entry_id: UUID


@dataclass(frozen=True, slots=True)
class Distribution:
    # (Start, Bahn) in der Reihenfolge der Vergabe.
    picks: list[tuple[UUID, int]]
    # Starts, die vor oder zwischen den Vergebenen standen, aber übersprungen wurden, weil ihre
    # Person schon auf einer Bahn steht (oder in diesem Durchlauf eine bekommen hat).
    skipped: list[UUID]


def distribute_lanes(
    free_lanes: Sequence[int], waiting: Sequence[Waiting], busy_entries: Iterable[UUID]
) -> Distribution:
    """Verteilt die Wartenden der Reihe nach auf die freien Bahnen.

    Wer schon auf einer Bahn steht (oder in diesem Durchlauf eine bekommt), wird übersprungen
    und bleibt an seinem Platz in der Reihenfolge. Übersprungen zählt nur, wer drangekommen
    wäre, solange noch eine Bahn frei war.
    """
    busy = set(busy_entries)
    lanes = list(free_lanes)
    picks: list[tuple[UUID, int]] = []
    skipped: list[UUID] = []
    for candidate in waiting:
        if not lanes:
            break
        if candidate.entry_id in busy:
            skipped.append(candidate.start_id)
            continue
        busy.add(candidate.entry_id)
        picks.append((candidate.start_id, lanes.pop(0)))
    return Distribution(picks=picks, skipped=skipped)


def pick_for_lanes(
    free_lanes: Sequence[int], waiting: Sequence[Waiting], busy_entries: Iterable[UUID]
) -> list[tuple[UUID, int]]:
    """Nur die Vergabe aus `distribute_lanes`."""
    return distribute_lanes(free_lanes, waiting, busy_entries).picks


# --- Zeitplan ----------------------------------------------------------------


def heat_series(first: datetime, count: int, minutes: int) -> list[tuple[datetime, datetime]]:
    """Zeitfenster für `count` Durchgänge zu je `minutes` Minuten, lückenlos hintereinander."""
    if count < 1 or minutes < 1:
        raise ValueError("count und minutes müssen mindestens 1 sein")
    step = timedelta(minutes=minutes)
    return [(first + i * step, first + (i + 1) * step) for i in range(count)]


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Ob sich zwei halboffene Zeitfenster [start, end) überschneiden."""
    return a_start < b_end and b_start < a_end


def first_free_lane(lane_count: int, taken: Iterable[int]) -> int | None:
    used = set(taken)
    return next((lane for lane in range(1, lane_count + 1) if lane not in used), None)


# --- Zeitplan und Reihenfolge auf einem Stand --------------------------------

# Schlüssel in `tournament.settings` (Modul `turnier`): So viele Minuten vor Beginn eines
# Durchgangs hält der Stand dessen gebuchte Bahnen für ihn frei; Aufrufe aus der Reihenfolge
# auf diese Bahnen brauchen dann eine Bestätigung. 0 = aus. Fehlt er (ältere Turniere), gilt
# der Standard.
HEAT_RESERVE_SETTING = "heat_reserve_minutes"
DEFAULT_HEAT_RESERVE_MINUTES = 10


def heat_reserve_minutes(settings: Mapping[str, Any]) -> int:
    value = settings.get(HEAT_RESERVE_SETTING, DEFAULT_HEAT_RESERVE_MINUTES)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return DEFAULT_HEAT_RESERVE_MINUTES
    return value


def heat_is_reserving(starts_at: datetime, ends_at: datetime, now: datetime, minutes: int) -> bool:
    """Ob ein Durchgang seine Bahnen jetzt freihält: Er beginnt innerhalb von `minutes`
    Minuten oder hat schon begonnen und ist noch nicht vorbei. Mit 0 Minuten nie."""
    if minutes <= 0:
        return False
    return starts_at - timedelta(minutes=minutes) <= now < ends_at


def lane_list(lanes: Iterable[int]) -> str:
    """„Bahn 3“, „Bahnen 1 und 3“, „Bahnen 1, 2 und 4“."""
    numbers = [str(lane) for lane in sorted(set(lanes))]
    if len(numbers) == 1:
        return f"Bahn {numbers[0]}"
    return f"Bahnen {', '.join(numbers[:-1])} und {numbers[-1]}"
