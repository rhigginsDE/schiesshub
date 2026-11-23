"""Ablauf einer Serie (`"status"` in den Rohwerten einer Serie).

Welche Status eine Serie haben darf, hängt von der Definition ab (`Definition.series_statuses`):

- `normal` – immer erlaubt und Standard, wenn `status` fehlt.
- `unfinished` – Serie nicht beendet; nur mit `scoring.unbeendete_serie` (Speed): Es zählen die
  bis dahin erfassten Schüsse und `time_cs` als Zeit des letzten Schusses.
- `time_limit`, `aborted_by_shooter` – Zeitlimit erreicht bzw. Abbruch durch den Schützen; nur mit
  `zeit_bei_abbruch_s` (Fallscheibe): Serienzeit = zeit_bei_abbruch_s + Zuschlag je stehender
  Scheibe; eine gemessene Zeit wird nicht gewertet.
- `malfunction_before_first_shot` – Waffenstörung vor dem ersten Wertungsschuss; nur mit
  `zuschlag_stoerung_vor_erstem_schuss_s`: Serienzeit = zeit_bei_abbruch_s + dieser Zuschlag.
"""

from typing import Literal

SeriesStatus = Literal[
    "normal", "unfinished", "time_limit", "aborted_by_shooter", "malfunction_before_first_shot"
]

NORMAL: SeriesStatus = "normal"
UNFINISHED: SeriesStatus = "unfinished"
MALFUNCTION: SeriesStatus = "malfunction_before_first_shot"
ABORTED_BY_SHOOTER: SeriesStatus = "aborted_by_shooter"
ABORTED: tuple[SeriesStatus, ...] = ("time_limit", "aborted_by_shooter")
FIXED_TIME: tuple[SeriesStatus, ...] = (*ABORTED, MALFUNCTION)
"""Status, bei denen statt der gemessenen Zeit `zeit_bei_abbruch_s` zählt."""

STATUS_LABELS: dict[SeriesStatus, str] = {
    "normal": "regulär",
    "unfinished": "Serie nicht beendet",
    "time_limit": "Zeitlimit erreicht (Abbruch durch den Schießleiter)",
    "aborted_by_shooter": "Abbruch durch den Schützen",
    "malfunction_before_first_shot": "Waffenstörung vor dem ersten Wertungsschuss",
}
