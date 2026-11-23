"""Voreinstellung der Planung aus dem Ablauf ableiten (docs/ARCHITEKTUR.md, Abschnitt
„Ablauf am Schießstand“).

Haben alle Abschnitte einer Variante eine feste Zeit je Serie (`zeit_je_serie_s`) oder eine
vollständige Zeitliste (`zeiten_s`), ist der Wettbewerb planbar: Zeitplan mit einer Dauer je
Durchgang aus der Summe der Serienzeiten, aufgerundet auf volle Minuten, plus Wechselzeit.
Sonst ist die Dauer nicht vorhersehbar, und es gilt die Reihenfolge.
"""

import math
from dataclasses import dataclass
from typing import Literal

from app.modules.katalog.fileformat import Abschnitt, Variante


@dataclass(frozen=True, slots=True)
class PlanningDefault:
    planning: Literal["queue", "schedule"]
    # Nur bei Zeitplan: Dauer eines Durchgangs einschließlich Wechselzeit.
    heat_minutes: int | None


def section_seconds(abschnitt: Abschnitt) -> float | None:
    """Feste Schießzeit eines Abschnitts in Sekunden; None, wenn sie nicht feststeht."""
    if abschnitt.zeiten_s is not None:
        return float(sum(abschnitt.zeiten_s))
    if abschnitt.zeit_je_serie_s is not None:
        return float(abschnitt.serien * abschnitt.zeit_je_serie_s)
    return None


def derive_planning(variant: Variante, changeover_minutes: int) -> PlanningDefault:
    total = 0.0
    for abschnitt in variant.abschnitte:
        seconds = section_seconds(abschnitt)
        if seconds is None:
            return PlanningDefault(planning="queue", heat_minutes=None)
        total += seconds
    return PlanningDefault(
        planning="schedule", heat_minutes=math.ceil(total / 60) + changeover_minutes
    )
