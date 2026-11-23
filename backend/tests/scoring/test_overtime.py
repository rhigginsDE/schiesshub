"""Modell `ringe_mit_zeitabzug` (Mehrdistanz), handgerechnet an KW Mehrdistanz Variante 1.

Fertigkeit: 46 + 43 + 41 + 43 = 173. Parcours: 48 + 45 + 42 + 47 = 182; Sollzeit 80 s,
Abbruchzeit 160 s, 1 Ring Abzug je voller Sekunde darüber, Teilergebnis mindestens 0.
Die Definitionen stammen aus `definitions.py` (ohne `positionen`); Positionen werden unten mit
eigenen Angaben geprüft.
"""

import copy
import re
from decimal import Decimal

import pytest

from app.scoring import DefinitionError, Issue, compute, describe_form, rank, validate_raw
from tests.scoring import definitions
from tests.scoring.support import contender

KW = definitions.mehrdistanz_kw()
FLINTE = definitions.mehrdistanz_flinte()  # Gleichstand: zehner, parcours_zeit
LW = definitions.mehrdistanz_lw()  # Gleichstand: parcours_zeit

FERTIGKEIT = [
    {"shots": [10, 10, 9, 9, 8]},
    {"shots": [10, 9, 9, 8, 7]},
    {"shots": [9, 9, 8, 8, 7]},
    {"shots": ["X", 10, 9, 8, 6]},
]
PARCOURS = [
    {"shots": [10, 10, 10, 9, 9]},
    {"shots": [10, 9, 9, 9, 8]},
    {"shots": [9, 9, 8, 8, 8]},
    {"shots": [10, 10, 9, 9, 9]},
]


def raw(parcours_time_cs: int | None, parcours: list[dict] = PARCOURS) -> dict:
    section: dict = {"series": parcours}
    if parcours_time_cs is not None:
        section["time_cs"] = parcours_time_cs
    return {"sections": {"fertigkeit": {"series": FERTIGKEIT}, "parcours": section}}


def test_full_seconds_over_target_time_are_deducted() -> None:
    result = compute(KW, "shot", raw(8399))  # 83,99 s → 3 volle Sekunden

    fertigkeit, parcours = result.sections
    assert (fertigkeit.result, parcours.rings, parcours.overtime_s) == (Decimal(173), 182, 3)
    assert parcours.deduction == Decimal(3)
    assert parcours.result == Decimal(179)
    assert result.score == Decimal(352)
    assert result.complete
    assert result.parcours_time_cs == 8399
    assert result.steps[-3:] == [
        "Parcours: 48 + 45 + 42 + 47 = 182 Ringe",
        "Parcours: Zeit 83,99 s, Sollzeit 80 s → 3 volle Sekunden darüber × 1 = 3 Ringe Abzug: "
        "182 − 3 = 179",
        "Ergebnis: Fertigkeit 173 + Parcours 179 = 352 Ringe",
    ]
    assert result.steps[0] == "Fertigkeit, Serie 1: 10 + 10 + 9 + 9 + 8 = 46 Ringe"


@pytest.mark.parametrize(
    ("time_cs", "deduction"),
    [(7000, 0), (8000, 0), (8099, 0), (8100, 1), (8199, 1), (9050, 10)],
)
def test_only_full_seconds_count(time_cs: int, deduction: int) -> None:
    result = compute(KW, "shot", raw(time_cs))
    assert result.sections[1].deduction == Decimal(deduction)
    assert result.score == Decimal(173 + 182 - deduction)


def test_within_target_time_says_so() -> None:
    result = compute(KW, "shot", raw(7950))
    assert "Parcours: Zeit 79,50 s innerhalb der Sollzeit von 80 s, kein Abzug" in result.steps


def test_partial_result_is_floored_at_zero_with_warning_over_abort_time() -> None:
    weak = [{"shots": [1, 1, 1, 1, 1]}] * 4  # 20 Ringe
    result = compute(KW, "shot", raw(16100, weak))  # 81 volle Sekunden über 80 s

    parcours = result.sections[1]
    assert (parcours.subtotal, parcours.result, parcours.floored) == (
        Decimal(-61),
        Decimal(0),
        True,
    )
    assert result.score == Decimal(173)
    assert "Parcours: Teilergebnis −61 liegt unter der Untergrenze 0 → 0" in result.steps
    assert [w.path for w in result.warnings] == ["sections.parcours.time_cs"]
    assert result.warnings[0].message.startswith(
        "Parcours: Gesamtzeit 161,00 s liegt über der Abbruchzeit von 160 s."
    )


def test_without_min_teilergebnis_the_section_may_go_negative() -> None:
    no_floor = copy.deepcopy(KW)
    del no_floor["scoring"]["min_teilergebnis"]
    weak = [{"shots": [1, 1, 1, 1, 1]}] * 4

    result = compute(no_floor, "shot", raw(16100, weak))

    assert result.sections[1].result == Decimal(-61)
    assert result.score == Decimal(173 - 61)


def test_missing_parcours_time() -> None:
    assert validate_raw(KW, "shot", raw(None), partial=False) == [
        Issue(path="sections.parcours.time_cs", message="Parcours: Gesamtzeit fehlt")
    ]
    result = compute(KW, "shot", raw(None))
    assert not result.complete
    assert result.score == Decimal(355)
    assert "Parcours: Gesamtzeit noch nicht erfasst, Abzug offen" in result.steps
    assert result.progress.section_times_entered == 0
    assert result.progress.section_times_expected == 1


def test_time_belongs_to_section_not_series() -> None:
    bad = raw(8000, [{**PARCOURS[0], "time_cs": 2000}, *PARCOURS[1:]])
    assert validate_raw(KW, "shot", bad) == [
        Issue(
            path="sections.parcours.series[0].time_cs",
            message="Parcours, Serie 1: "
            "die Zeit wird für den ganzen Abschnitt erfasst, nicht je Serie",
        )
    ]


def test_form_has_section_time_distances_and_hints() -> None:
    form = describe_form(KW, "shot")
    fertigkeit, parcours = form.sections

    assert fertigkeit.fields == []
    assert [s.distance_m for s in fertigkeit.series] == [Decimal(d) for d in (5, 10, 15, 20)]
    assert fertigkeit.series[0].hints == ["Distanz 5 m", "5 Schuss", "Schießzeit 10 s"]
    assert [(f.key, f.label, f.unit) for f in parcours.fields] == [("time_cs", "Gesamtzeit", "cs")]
    assert parcours.hints == ["Sollzeit 80 s", "Abbruchzeit 160 s"]
    assert parcours.target_time_s == Decimal(80)
    assert [s.distance_m for s in parcours.series] == [Decimal(d) for d in (20, 15, 10, 5)]
    assert form.max_rings == 400


def test_parcours_time_breaks_ties_for_flinte() -> None:
    three = FERTIGKEIT[:3]

    def start(ident: str, time_cs: int) -> object:
        data = raw(time_cs, PARCOURS[:3])
        data["sections"]["fertigkeit"]["series"] = three
        return contender(FLINTE, data, ident)

    # Sollzeit 70 s: beide unter der Sollzeit → gleiche Ringe und Zehner, kürzere Zeit gewinnt.
    slow, fast = start("langsam", 6900), start("schnell", 6500)
    assert [(p.id, p.place, p.tied) for p in rank([slow, fast])] == [
        ("schnell", 1, False),
        ("langsam", 2, False),
    ]


def test_parcours_time_is_the_only_tie_breaker_for_lw() -> None:
    def start(ident: str, time_cs: int, first: list) -> object:
        data = {
            "sections": {
                "fertigkeit": {"series": [{"shots": first}, *[{"shots": [9] * 5}] * 2]},
                "parcours": {"series": [{"shots": [9] * 5}] * 3, "time_cs": time_cs},
            }
        }
        return contender(LW, data, ident)

    # Gleiche Ringe, aber unterschiedlich viele Zehner: bei LW entscheidet nur die Parcourszeit.
    tens = start("zehner", 6000, [10, 10, 8, 8, 9])
    quick = start("schnell", 5000, [9, 9, 9, 9, 9])
    assert [p.id for p in rank([tens, quick])] == ["schnell", "zehner"]


def test_missing_abzug_is_an_error() -> None:
    broken = copy.deepcopy(KW)
    del broken["scoring"]["abzug_je_voller_sekunde_ueber_sollzeit"]
    with pytest.raises(
        DefinitionError, match="abzug_je_voller_sekunde_ueber_sollzeit: Pflichtangabe"
    ):
        compute(broken, "shot", {})


# --- Positionen (optional, nur Hinweis) --------------------------------------

POSITIONS = [
    {
        "nr": 5,
        "distanz_m": 20,
        "anschlaege": [{"haltung": "stehend", "hand": "beidhaendig"}],
        "scheibe": 1,
    },
    {
        "nr": 6,
        "distanz_m": 15,
        "anschlaege": [
            {"haltung": "kniend", "hand": "beidhaendig"},
            {"haltung": "stehend", "hand": "schwache_hand"},
        ],
        "scheibe": 2,
    },
    {"nr": 7, "anschlaege": [{"haltung": "liegend"}]},
    {"nr": 8, "distanz_m": 5, "anschlaege": [{"haltung": "stehend", "hand": "einhaendig"}]},
]


def with_positions(positions: list[dict]) -> dict:
    changed = copy.deepcopy(KW)
    changed["variant"]["abschnitte"][1]["positionen"] = positions
    return changed


def test_positions_are_accepted_and_shown_but_do_not_change_the_score() -> None:
    positioned = with_positions(POSITIONS)
    form = describe_form(positioned, "shot")
    fertigkeit, parcours = form.sections

    # Abschnitt ohne positionen: keine Positionsangaben.
    assert all(series.position is None for series in fertigkeit.series)
    first, second, third = parcours.series[:3]
    assert first.position is not None
    assert (first.position.nr, first.position.distance_m, first.position.target) == (
        5,
        Decimal(20),
        1,
    )
    assert first.hints[0] == "Position 5: stehend, beidhändig, Scheibe 1"
    assert (
        second.hints[0] == "Position 6: kniend, beidhändig oder stehend, schwache Hand, Scheibe 2"
    )
    assert [s.text for s in second.position.stances] == [
        "kniend, beidhändig",
        "stehend, schwache Hand",
    ]
    assert third.hints[0] == "Position 7: liegend"
    assert third.distance_m == Decimal(10)  # aus distanzen_m
    assert form.model_dump(mode="json")["sections"][1]["series"][1]["position"]["stances"][1] == {
        "haltung": "stehend",
        "hand": "schwache_hand",
        "text": "stehend, schwache Hand",
    }

    assert compute(positioned, "shot", raw(8399)).score == compute(KW, "shot", raw(8399)).score


@pytest.mark.parametrize(
    ("positions", "message"),
    [
        (POSITIONS[:3], "positionen hat 3 Einträge, erwartet werden 4"),
        ([{**POSITIONS[0], "distanz_m": 25}, *POSITIONS[1:]], "positionen[0].distanz_m ist 25"),
        ([{**POSITIONS[0], "anschlaege": []}, *POSITIONS[1:]], "anschlaege"),
        ([{**POSITIONS[0], "anschlaege": [{"haltung": "hockend"}]}, *POSITIONS[1:]], "haltung"),
        (
            [
                {**POSITIONS[0], "anschlaege": [{"haltung": "kniend", "hand": "links"}]},
                *POSITIONS[1:],
            ],
            "hand",
        ),
        ([{**POSITIONS[0], "farbe": "rot"}, *POSITIONS[1:]], "farbe: unbekanntes Feld"),
    ],
)
def test_invalid_positions(positions: list[dict], message: str) -> None:
    with pytest.raises(DefinitionError, match=re.escape(message)):
        describe_form(with_positions(positions), "shot")
