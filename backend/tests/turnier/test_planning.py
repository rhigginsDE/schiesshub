"""Ableitung der Planung aus dem Ablauf (reine Funktion, ohne Datenbank)."""

from typing import Any

import pytest

from app.modules.katalog.fileformat import Variante
from app.modules.turnier.planning import PlanningDefault, derive_planning


def variant(*sections: dict[str, Any]) -> Variante:
    return Variante.model_validate(
        {
            "id": "standard",
            "name": "Standard",
            "abschnitte": [
                {"id": f"abschnitt-{index}", "name": f"Abschnitt {index}", **section}
                for index, section in enumerate(sections)
            ],
        }
    )


def test_fixed_time_per_series_gives_schedule() -> None:
    # Präzision: 2 × 10 Schuss in je 5 Minuten.
    praezision = variant({"serien": 2, "schuss_je_serie": 10, "zeit_je_serie_s": 300})

    assert derive_planning(praezision, changeover_minutes=5) == PlanningDefault("schedule", 15)


def test_time_list_is_summed() -> None:
    zeitserie = variant({"serien": 3, "schuss_je_serie": 5, "zeiten_s": [40, 30, 20]})

    assert derive_planning(zeitserie, changeover_minutes=0) == PlanningDefault("schedule", 2)


def test_seconds_are_rounded_up_to_full_minutes() -> None:
    # 2 × 45 s = 90 s → 2 Minuten, nicht 1,5.
    speed = variant({"serien": 2, "schuss_je_serie": 5, "zeit_je_serie_s": 45})

    assert derive_planning(speed, changeover_minutes=3) == PlanningDefault("schedule", 5)


def test_fractional_seconds() -> None:
    exact = variant({"serien": 4, "schuss_je_serie": 1, "zeit_je_serie_s": 15.0})
    slightly_more = variant({"serien": 4, "schuss_je_serie": 1, "zeit_je_serie_s": 15.25})

    assert derive_planning(exact, changeover_minutes=0).heat_minutes == 1
    assert derive_planning(slightly_more, changeover_minutes=0).heat_minutes == 2


def test_all_sections_count() -> None:
    kombi = variant(
        {"serien": 1, "schuss_je_serie": 10, "zeit_je_serie_s": 300},
        {"serien": 2, "schuss_je_serie": 5, "zeiten_s": [20, 10]},
    )

    # 300 s + 30 s = 330 s → 6 Minuten, plus 4 Minuten Wechsel.
    assert derive_planning(kombi, changeover_minutes=4) == PlanningDefault("schedule", 10)


@pytest.mark.parametrize(
    "section",
    [
        # Fallscheibe: nur eine Obergrenze, die Zeit wird gemessen.
        {"serien": 4, "ziele_je_serie": 5, "max_zeit_je_serie_s": 60, "zeit_wird_gemessen": True},
        # Intervall: Zeit je Schuss, keine Zeit je Serie.
        {"serien": 2, "schuss_je_serie": 5, "zeit_je_schuss_s": 3},
        # Mehrdistanz-Parcours: Sollzeit für den ganzen Abschnitt.
        {"serien": 1, "schuss_je_serie": 12, "sollzeit_s": 60},
        # Gar keine Zeit.
        {"serien": 2, "schuss_je_serie": 10},
    ],
)
def test_without_fixed_time_gives_queue(section: dict[str, Any]) -> None:
    assert derive_planning(variant(section), changeover_minutes=5) == PlanningDefault("queue", None)


def test_one_open_section_makes_the_whole_variant_a_queue() -> None:
    mixed = variant(
        {"serien": 2, "schuss_je_serie": 10, "zeit_je_serie_s": 300},
        {"serien": 4, "ziele_je_serie": 5, "max_zeit_je_serie_s": 60},
    )

    assert derive_planning(mixed, changeover_minutes=5) == PlanningDefault("queue", None)
