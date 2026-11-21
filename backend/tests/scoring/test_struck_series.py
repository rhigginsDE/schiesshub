"""`serien_gewertet` (nur die ersten N Serien zählen) und `trefferaufnahme_nach` (nur Kennzeichen).

Typischer Fall: Ein Turnier reduziert nach dem Start von 6 auf 4 Serien. Starts mit 6 und mit 4
erfassten Serien müssen dann gleich behandelt werden.
"""

import pytest

from app.scoring import DefinitionError, Issue, compute, describe_form, rank, rank_key, validate_raw
from tests.scoring import definitions
from tests.scoring.support import contender, series_of


def reduced(base: dict, counted: int, breaks: list[int] | None = None) -> dict:
    section = base["variant"]["abschnitte"][0]
    section["serien_gewertet"] = counted
    if breaks is not None:
        section["trefferaufnahme_nach"] = breaks
    return base


RINGE_6 = definitions.intervall(6)
RINGE_4_OF_6 = reduced(definitions.intervall(6), 4, [2, 4])

# 46 (2 Zehner) · 46 (1 Zehner, 1 Innenzehner) · 43 · 40 (1 Zehner) | gestrichen: 50 · 49
INTERVALL = [
    {"shots": [10, 10, 9, 9, 8]},
    {"shots": ["X", 9, 9, 9, 9]},
    {"shots": [9, 9, 9, 8, 8]},
    {"shots": [10, 9, 8, 7, 6]},
    {"shots": [10, 10, 10, 10, 10]},
    {"shots": [10, 10, 10, 10, 9]},
]


def intervall(*series: dict) -> dict:
    return series_of(*series, section="intervall")


def test_rings_only_first_series_count() -> None:
    result = compute(RINGE_4_OF_6, "shot", intervall(*INTERVALL))

    assert result.score == 175
    assert (result.rings, result.tens, result.inner_tens) == (175, 4, 1)
    assert result.ring_counts is not None
    assert result.ring_counts[10] == 4
    assert result.complete
    assert result.progress.model_dump() == {
        "shots_entered": 20,
        "shots_expected": 20,
        "series_complete": 4,
        "series_expected": 4,
        "section_times_entered": 0,
        "section_times_expected": 0,
    }
    series = result.sections[0].series
    assert [(s.number, s.struck, s.rings) for s in series] == [
        (1, False, 46),
        (2, False, 46),
        (3, False, 43),
        (4, False, 40),
        (5, True, 50),
        (6, True, 49),
    ]
    assert result.sections[0].rings == 175
    assert "Serie 5 und 6 gestrichen (nicht gewertet)" in result.steps
    assert not any(step.startswith("Serie 5:") for step in result.steps)
    assert result.steps[-2:] == ["Intervall: 46 + 46 + 43 + 40 = 175 Ringe", "Ergebnis: 175 Ringe"]
    assert compute(RINGE_6, "shot", intervall(*INTERVALL)).score == 274


def test_struck_series_are_optional_but_validated() -> None:
    assert validate_raw(RINGE_4_OF_6, "shot", intervall(*INTERVALL[:4]), partial=False) == []
    assert validate_raw(RINGE_4_OF_6, "shot", intervall(*INTERVALL), partial=False) == []
    # Unvollständig darf eine gestrichene Serie sein, falsch nicht.
    partly = intervall(*INTERVALL[:4], {"shots": [10, 10]})
    assert validate_raw(RINGE_4_OF_6, "shot", partly, partial=False) == []
    wrong = intervall(*INTERVALL[:4], {"shots": [11]})
    assert validate_raw(RINGE_4_OF_6, "shot", wrong, partial=False) == [
        Issue(
            path="sections.intervall.series[4].shots[0]",
            message="Serie 5, Schuss 1: Ringwert 0 bis 10 oder „X“ (Innenzehner), nicht 11",
        )
    ]
    # Fehlt eine gewertete Serie, bleibt es ein Fehler.
    assert validate_raw(RINGE_4_OF_6, "shot", intervall(*INTERVALL[:3]), partial=False) == [
        Issue(path="sections.intervall.series[3]", message="Serie 4 fehlt")
    ]


def test_reduction_after_start_ranks_six_and_four_series_alike() -> None:
    six = contender(RINGE_4_OF_6, intervall(*INTERVALL), "sechs")
    four = contender(RINGE_4_OF_6, intervall(*INTERVALL[:4]), "vier")
    better = contender(
        RINGE_4_OF_6, intervall(*INTERVALL[:3], {"shots": [10, 9, 8, 7, 7]}), "besser"
    )  # 176

    assert six.key == four.key
    assert six.complete
    assert four.complete
    assert [(p.id, p.place, p.tied) for p in rank([six, four, better])] == [
        ("besser", 1, False),
        ("sechs", 2, True),
        ("vier", 2, True),
    ]
    # Ohne Reduktion läge der Start mit sechs Serien vorn.
    assert contender(RINGE_6, intervall(*INTERVALL), "a").key > rank_key(
        RINGE_6, compute(RINGE_6, "shot", intervall(*INTERVALL[:4]))
    )


def test_form_marks_struck_series_and_scoring_breaks() -> None:
    form = describe_form(RINGE_4_OF_6, "shot")
    section = form.sections[0]

    assert (form.series_expected, form.shots_expected, form.max_rings) == (4, 20, 200)
    assert (section.series_counted, section.max_rings) == (4, 200)
    assert [s.struck for s in section.series] == [False] * 4 + [True] * 2
    assert [s.scoring_break_after for s in section.series] == [
        False,
        True,
        False,
        True,
        False,
        False,
    ]
    assert section.series[1].hints[-1] == "danach Trefferaufnahme"
    struck = section.series[4]
    assert struck.hints[0] == "gestrichen (nicht gewertet)"
    assert [(f.key, f.required) for f in struck.fields] == [("shots", False)]
    assert [(f.key, f.required) for f in section.series[0].fields] == [("shots", True)]
    dumped = form.model_dump(mode="json")["sections"][0]["series"][4]
    assert (dumped["struck"], dumped["scoring_break_after"]) == (True, False)


def test_scoring_breaks_alone_do_not_change_anything() -> None:
    with_breaks = definitions.intervall(6)
    with_breaks["variant"]["abschnitte"][0]["trefferaufnahme_nach"] = [3, 6]
    raw = intervall(*INTERVALL)

    assert compute(with_breaks, "shot", raw) == compute(RINGE_6, "shot", raw)
    form = describe_form(with_breaks, "shot")
    assert [s.scoring_break_after for s in form.sections[0].series] == [
        False,
        False,
        True,
        False,
        False,
        True,
    ]
    assert form.series_expected == 6


# --- Fallscheibe -----------------------------------------------------------------

FALLSCHEIBE_4_OF_6 = reduced(definitions.fallscheibe(6), 4)

# 22,84 · 9,90 · 78,10 · 15,00 = 125,84 s | gestrichen: 9,00 s · 61,20 s + 5 × 10 s
FALLSCHEIBE = [
    {"time_cs": 1284, "standing": 1},
    {"time_cs": 990, "standing": 0},
    {"time_cs": 5810, "standing": 2},
    {"time_cs": 1500, "standing": 0},
    {"time_cs": 900, "standing": 0},
    {"time_cs": 6120, "standing": 5},
]


def fallscheibe(*series: dict) -> dict:
    return series_of(*series, section="fallscheibe")


def test_fallscheibe_only_first_series_count() -> None:
    result = compute(FALLSCHEIBE_4_OF_6, "shot", fallscheibe(*FALLSCHEIBE))

    assert str(result.score) == "125.84"
    assert (result.time_cs, result.penalty_cs) == (9584, 3000)
    assert result.complete
    assert result.warnings == []  # die gestrichene 61,20 s löst keine Warnung aus
    assert [(s.struck, s.total_cs) for s in result.sections[0].series[4:]] == [
        (True, 900),
        (True, 11120),
    ]
    assert result.steps[4:] == [
        "Serie 5 und 6 gestrichen (nicht gewertet)",
        "Ergebnis: 22,84 s + 9,90 s + 78,10 s + 15,00 s = 125,84 s",
    ]


def test_fallscheibe_reduction_ranks_six_and_four_series_alike() -> None:
    six = contender(FALLSCHEIBE_4_OF_6, fallscheibe(*FALLSCHEIBE), "sechs")
    four = contender(FALLSCHEIBE_4_OF_6, fallscheibe(*FALLSCHEIBE[:4]), "vier")
    slower = contender(
        FALLSCHEIBE_4_OF_6, fallscheibe(*FALLSCHEIBE[:3], {"time_cs": 1501, "standing": 0}), "x"
    )

    assert six.key == four.key == [-12584]
    assert [(p.id, p.place) for p in rank([slower, four, six])] == [
        ("vier", 1),
        ("sechs", 1),
        ("x", 3),
    ]


def test_speed_counts_only_times_of_counted_series() -> None:
    definition = reduced(definitions.speed(6), 4)
    full = {"shots": [10] * 5, "time_cs": 1000}
    struck = {"shots": [0] * 5, "time_cs": 5999}
    result = compute(definition, "shot", series_of(*[full] * 4, struck, struck, section="speed"))
    assert result.score == 200 - 40
    assert result.time_cs == 4000


def test_single_struck_series_step() -> None:
    result = compute(reduced(definitions.intervall(6), 5), "shot", intervall(*INTERVALL))
    assert "Serie 6 gestrichen (nicht gewertet)" in result.steps
    assert result.score == 225


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"serien_gewertet": 7}, "serien_gewertet ist 7, es gibt nur 6 Serien"),
        ({"serien_gewertet": 0}, "serien_gewertet"),
        ({"trefferaufnahme_nach": [4, 2]}, "aufsteigend und ohne Doppelte"),
        ({"trefferaufnahme_nach": [2, 2]}, "aufsteigend und ohne Doppelte"),
        ({"trefferaufnahme_nach": [7]}, "Seriennummern höchstens 6"),
    ],
)
def test_invalid_fields(fields: dict, message: str) -> None:
    definition = definitions.intervall(6)
    definition["variant"]["abschnitte"][0].update(fields)
    with pytest.raises(DefinitionError) as caught:
        describe_form(definition, "shot")
    assert any(message in problem for problem in caught.value.problems), caught.value.problems
