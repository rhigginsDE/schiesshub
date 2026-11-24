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

Was bei welchem Status gewertet wird, steht an einer Stelle: `field_role`. Maske
(`form.StatusOption`), Prüfung (`raw.py`) und Rechenweg (`compute.py`) richten sich danach.
Erfasste Werte gehen nie verloren: Jeder Schlüssel, den die Maske für eine Serie kennt, wird
bei jedem Status angenommen und unverändert gespeichert, auch wenn er nicht zählt.
"""

from typing import Literal

FieldRole = Literal["required", "optional", "unscored"]
"""`required`: gewertet und für ein vollständiges Ergebnis nötig; `optional`: gewertet, wenn
erfasst (Zehner/Innenzehner für den Gleichstand); `unscored`: darf erfasst sein, bleibt in den
Rohwerten, zählt aber nicht (der Rechenweg nennt den Wert)."""

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

SERIES_FIELD_KEYS = ("shots", "sum", "tens", "inner_tens", "time_cs", "standing")
"""Wertfelder einer Serie (ohne `status`)."""


def field_role(status: SeriesStatus, key: str) -> FieldRole:
    """Was ein Wertfeld der Serie bei diesem Status bedeutet (`FieldRole`).

    Gilt für jedes Feld, das die Maske für die Serie hat; welche Felder es gibt, hängt vom
    Abschnitt ab (Ringe, Zeit je Serie, stehende Scheiben). Fundstellen: BDS-SHB, Fassung
    BVA-Bescheid 30.06.2026 (Katalogkommentare in `catalog/bds/gruppen/*.yaml`).
    """
    match key:
        case "shots" | "sum":
            # Ringe zählen bei jedem Status:
            # - normal: Regelfall.
            # - unfinished: die bis dahin erzielten Ringe (K 6.10, L 9.09; README
            #   `unbeendete_serie`) – als Einzelschüsse oder als Summe der bis dahin
            #   erzielten Ringe.
            # - time_limit, aborted_by_shooter, malfunction_before_first_shot: Die Ringmodelle
            #   lassen `zeit_bei_abbruch_s` nicht zu (`models._no_abort_rules`), Fallscheibe
            #   wertet keine Ringe – die Kombination kommt derzeit nicht vor. Käme sie, zählte
            #   das bis dahin erzielte Ergebnis (K 1.14, L 1.12; kein Nachholen, A 9.08).
            # Pflicht ist der Wert, weil `validate_raw` für ein vollständiges Ergebnis bei jedem
            # Status Ringe verlangt (unverändertes Verhalten).
            return "required"
        case "tens" | "inner_tens":
            # Freiwillig bei Seriensumme, gewertet für den Gleichstand (`gleichstand`).
            return "optional"
        case "time_cs":
            # Abbruch und Störung: Es zählt `zeit_bei_abbruch_s`, nicht die gemessene Zeit
            # (K 5.09, K 5.19 → K 5.09, L 8.09, L 10.09 → L 8.09). Nicht beendet: Zeit des
            # letzten Schusses (K 6.10, L 9.09).
            return "unscored" if status in FIXED_TIME else "required"
        case "standing":
            # Störung vor dem ersten Wertungsschuss: Abbruchzeit plus Strafzeit (K 5.09,
            # L 8.09); ein Zuschlag je stehender Scheibe ist dafür nicht vorgesehen, er zählt
            # nicht (bisheriges Verhalten).
            # Zeitlimit und Abbruch durch den Schützen: feste Serienzeit plus Zuschlag je
            # stehender Scheibe (K 5.09, L 8.09; wie `TimePlusPenalties.unshot_series`).
            return "unscored" if status == MALFUNCTION else "required"
    raise ValueError(f"unbekanntes Feld der Serie: {key}")
