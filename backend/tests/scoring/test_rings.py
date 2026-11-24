"""Modell `ringe`, handgerechnet an KW 25 m Präzision (2×10 Schuss) und KW 25 m Kombi."""

from decimal import Decimal

import pytest

from app.scoring import InvalidRawError, Issue, compute, describe_form, rank, validate_raw
from tests.scoring import definitions
from tests.scoring.support import contender, series_of

PRAEZISION = definitions.praezision()
KOMBI = definitions.kombi()

# 10+9+9+10+8+10+7+9+10+10 = 92 (5 Zehner, davon 2 Innenzehner)
S1 = [10, 9, 9, "X", 8, 10, 7, 9, 10, "X"]
# 9+9+8+8+10+7+6+9+10+0 = 76 (2 Zehner)
S2 = [9, 9, 8, 8, 10, 7, 6, 9, 10, 0]


def raw(*series: dict) -> dict:
    return series_of(*series, section="praezision")


def test_single_shots_hand_computed() -> None:
    result = compute(PRAEZISION, "shot", raw({"shots": S1}, {"shots": S2}))

    assert result.score == Decimal(168)
    assert result.score_text == "168 Ringe"
    assert result.complete
    assert (result.tens, result.inner_tens) == (7, 2)
    assert result.ring_counts == {10: 7, 9: 6, 8: 3, 7: 2, 6: 1, 5: 0, 4: 0, 3: 0, 2: 0, 1: 0, 0: 1}
    assert [s.rings for s in result.sections[0].series] == [92, 76]
    assert result.steps == [
        "Serie 1: 10 + 9 + 9 + X + 8 + 10 + 7 + 9 + 10 + X = 92 Ringe",
        "Serie 2: 9 + 9 + 8 + 8 + 10 + 7 + 6 + 9 + 10 + 0 = 76 Ringe",
        "Präzision: 92 + 76 = 168 Ringe",
        "Ergebnis: 168 Ringe",
    ]
    assert result.tie_breakers_missing == []


def test_partial_counts_only_entered_shots() -> None:
    result = compute(PRAEZISION, "shot", raw({"shots": [10, 9, 9, "X"]}))

    assert result.score == Decimal(38)
    assert not result.complete
    assert result.progress.model_dump() == {
        "shots_entered": 4,
        "shots_expected": 20,
        "series_complete": 0,
        "series_expected": 2,
        "section_times_entered": 0,
        "section_times_expected": 0,
    }
    assert result.steps[0] == "Serie 1: 10 + 9 + 9 + X = 38 Ringe (4 von 10 Schuss)"


def test_missing_shots_are_never_filled_with_zero() -> None:
    issues = validate_raw(PRAEZISION, "shot", raw({"shots": S1[:7]}, {"shots": S2}), partial=False)

    assert issues == [
        Issue(
            path="sections.praezision.series[0].shots", message="Serie 1: 7 von 10 Schuss erfasst"
        )
    ]
    # Mit eingegebenen Nullen ist die Serie vollständig.
    filled = raw({"shots": [*S1[:7], 0, 0, 0]}, {"shots": S2})
    assert validate_raw(PRAEZISION, "shot", filled, partial=False) == []
    assert compute(PRAEZISION, "shot", filled).score == Decimal(63 + 76)


def test_series_sum_with_optional_tens() -> None:
    result = compute(
        PRAEZISION, "series", raw({"sum": 92, "tens": 5, "inner_tens": 2}, {"sum": 76, "tens": 2})
    )

    assert result.score == Decimal(168)
    assert (result.tens, result.inner_tens, result.ring_counts) == (7, None, None)
    # „Neuner abwärts“ braucht Einzelschüsse: bei Seriensumme fehlt es nicht, es geht nicht.
    assert result.tie_breakers_missing == ["innenzehner"]
    assert result.steps[0] == "Serie 1: Seriensumme 92 Ringe, 5 Zehner, 2 Innenzehner"


def test_series_sum_without_tens_marks_all_tie_breakers_missing() -> None:
    result = compute(PRAEZISION, "series", raw({"sum": 92}, {"sum": 76}))

    assert result.score == Decimal(168)
    assert result.tie_breakers_missing == ["zehner", "innenzehner"]


def test_mixed_capture_in_one_start() -> None:
    result = compute(PRAEZISION, "shot", raw({"shots": S1}, {"sum": 76, "tens": 2}))

    assert result.score == Decimal(168)
    assert result.tens == 7
    assert result.inner_tens is None  # Serie 2 ohne Innenzehner-Angabe
    assert result.ring_counts is None


@pytest.mark.parametrize(
    ("series", "path", "message"),
    [
        (
            {"shots": [11]},
            "shots[0]",
            "Serie 1, Schuss 1: Ringwert 0 bis 10 oder „X“ (Innenzehner), nicht 11",
        ),
        (
            {"shots": ["x"]},
            "shots[0]",
            "Serie 1, Schuss 1: Ringwert 0 bis 10 oder „X“ (Innenzehner), nicht 'x'",
        ),
        (
            {"shots": [True]},
            "shots[0]",
            "Serie 1, Schuss 1: Ringwert 0 bis 10 oder „X“ (Innenzehner), nicht True",
        ),
        (
            {"shots": [9.5]},
            "shots[0]",
            "Serie 1, Schuss 1: Ringwert 0 bis 10 oder „X“ (Innenzehner), nicht 9.5",
        ),
        ({"shots": [9] * 11}, "shots", "Serie 1: höchstens 10 Schuss, erfasst 11"),
        ({"sum": 101}, "sum", "Serie 1: Seriensumme: ganze Zahl von 0 bis 100"),
        ({"sum": 40, "tens": 5}, "sum", "Serie 1: 5 Zehner ergeben mindestens 50"),
        ({"sum": 99, "tens": 8}, "sum", "Serie 1: mit 8 Zehnern sind höchstens 98 Ringe möglich"),
        (
            {"sum": 92, "tens": 2, "inner_tens": 3},
            "inner_tens",
            "Serie 1: 3 Innenzehner, aber nur 2 Zehner (Innenzehner zählen mit)",
        ),
        (
            {"shots": [9], "sum": 9},
            "",
            "Serie 1: entweder Einzelschüsse oder Seriensumme, nicht beides",
        ),
        ({"time_cs": 900}, "time_cs", "Serie 1: dieser Abschnitt misst keine Zeit"),
        (
            {"standing": 1},
            "standing",
            "Serie 1: dieser Abschnitt hat keine Zuschläge für stehende Scheiben",
        ),
    ],
)
def test_invalid_series(series: dict, path: str, message: str) -> None:
    full_path = "sections.praezision.series[0]" + (f".{path}" if path else "")
    issues = validate_raw(PRAEZISION, "shot", raw(series))

    assert issues == [Issue(path=full_path, message=message)]
    with pytest.raises(InvalidRawError) as caught:
        compute(PRAEZISION, "shot", raw(series))
    assert caught.value.issues == issues


@pytest.mark.parametrize(
    ("raw_values", "path", "message"),
    [
        ([], "", "Rohwerte müssen ein Objekt sein"),
        ({"sections": {}, "extra": 1}, "extra", "unbekanntes Feld"),
        (
            {"sections": {"speed": {}}},
            "sections.speed",
            "unbekannter Abschnitt „speed“ (bekannt: praezision)",
        ),
        (
            {"sections": {"praezision": {"series": [{}, {}, {}]}}},
            "sections.praezision.series",
            "Präzision: höchstens 2 Serien, erfasst 3",
        ),
        (
            {"sections": {"praezision": {"series": [], "time_cs": 5}}},
            "sections.praezision.time_cs",
            "Präzision: Gesamtzeit gibt es nur bei Abschnitten mit Sollzeit",
        ),
        (
            {"sections": {"praezision": {"series": "92"}}},
            "sections.praezision.series",
            "Präzision: Serien müssen eine Liste sein",
        ),
    ],
)
def test_invalid_structure(raw_values: object, path: str, message: str) -> None:
    assert validate_raw(PRAEZISION, "shot", raw_values) == [Issue(path=path, message=message)]


def test_complete_check_requires_every_series() -> None:
    issues = validate_raw(PRAEZISION, "shot", raw({"shots": S1}, None), partial=False)
    assert issues == [Issue(path="sections.praezision.series[1]", message="Serie 2 fehlt")]
    assert validate_raw(PRAEZISION, "shot", {}, partial=False) == [
        Issue(path="sections.praezision", message="Präzision: Abschnitt fehlt")
    ]
    assert validate_raw(PRAEZISION, "shot", {}, partial=True) == []


def test_kombi_sums_sections_and_names_them() -> None:
    five = {"shots": [10, 10, 9, 9, 8]}  # 46
    result = compute(
        KOMBI,
        "shot",
        {
            "sections": {
                "praezision": {"series": [{"shots": S1}, {"shots": S2}]},
                "intervall": {"series": [five, {"shots": [9, 9, 9, 9, 9]}]},
                "zeitserie": {
                    "series": [{"shots": ["X", 10, 10, 10, 10]}, {"shots": [0, 0, 0, 0, 0]}]
                },
            }
        },
    )

    assert [s.result for s in result.sections] == [Decimal(168), Decimal(91), Decimal(50)]
    assert result.score == Decimal(309)
    assert result.steps[0].startswith("Präzision, Serie 1: ")
    assert result.steps[-1] == "Ergebnis: Präzision 168 + Intervall 91 + Zeitserie 50 = 309 Ringe"
    assert result.progress.shots_expected == 40


def test_form_for_single_shots_and_series_sum() -> None:
    shot = describe_form(KOMBI, "shot")
    series = describe_form(KOMBI, "series")

    assert shot.max_rings == 400
    assert shot.shots_expected == 40
    first = shot.sections[0].series[0]
    assert first.label == "Präzision, Serie 1"
    assert first.path == "sections.praezision.series[0]"
    assert [f.key for f in first.fields] == ["shots"]
    assert first.fields[0].count == 10
    assert first.fields[0].allowed_values == ["X", 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
    assert first.hints == ["10 Schuss", "Schießzeit 300 s"]
    assert shot.sections[1].series[0].hints == ["5 Schuss", "je Schuss 3 s Sicht, 7 s Pause"]
    assert shot.sections[2].series[1].hints == ["5 Schuss", "Schießzeit 10 s"]

    sum_fields = series.sections[0].series[0].fields
    assert [(f.key, f.required, f.max) for f in sum_fields] == [
        ("sum", True, 100),
        ("tens", False, 10),
        ("inner_tens", False, 10),
    ]
    assert series.notes[0].startswith("Bei Seriensumme lässt sich ein Gleichstand nicht")


def test_ties_resolved_by_tens_inner_tens_and_nines_down() -> None:
    def start(ident: str, shots: list) -> object:
        return contender(PRAEZISION, raw({"shots": shots}, {"shots": [0] * 10}), ident)

    more_tens = start("zehner", [10, 10, 10, 9, 9, 9, 9, 8, 8, 8])  # 90, 3 Zehner
    fewer_tens = start("weniger", [10, 10, 9, 9, 9, 9, 9, 9, 8, 8])  # 90, 2 Zehner
    inner = start("innen", [10, "X", 9, 9, 9, 9, 9, 9, 8, 8])  # 90, 2 Zehner, 1 Innenzehner
    nines = start("neuner", [10, 10, 9, 9, 9, 9, 9, 9, 9, 7])  # 90, 2 Zehner, mehr Neuner
    best = start("bester", [10] * 9 + [9])  # 99

    placements = rank([fewer_tens, nines, inner, more_tens, best])

    assert [(p.id, p.place, p.tied) for p in placements] == [
        ("bester", 1, False),
        ("zehner", 2, False),
        ("innen", 3, False),
        ("neuner", 4, False),
        ("weniger", 5, False),
    ]


def test_identical_results_share_place() -> None:
    same = [10, 9, 9, 9, 9, 9, 9, 9, 9, 9]
    a = contender(PRAEZISION, raw({"shots": same}, {"shots": S2}), "a")
    b = contender(PRAEZISION, raw({"shots": list(reversed(same))}, {"shots": S2}), "b")
    c = contender(PRAEZISION, raw({"shots": S1}, {"shots": S2}), "c")
    d = contender(PRAEZISION, raw({"shots": S2}, {"shots": S2}), "d")

    placements = rank([d, a, b, c])

    assert [(p.id, p.place, p.tied, p.tie_unresolved) for p in placements] == [
        ("c", 1, False, False),
        ("a", 2, True, False),
        ("b", 2, True, False),
        ("d", 4, False, False),
    ]


def test_series_sum_tie_falls_back_and_is_flagged_unresolvable() -> None:
    with_tens = contender(
        PRAEZISION, raw({"sum": 90, "tens": 3}, {"sum": 80, "tens": 1}), "a", "series"
    )
    fewer = contender(
        PRAEZISION, raw({"sum": 90, "tens": 2}, {"sum": 80, "tens": 1}), "b", "series"
    )
    also = contender(PRAEZISION, raw({"sum": 90, "tens": 2}, {"sum": 80, "tens": 1}), "c", "series")

    placements = rank([fewer, with_tens, also])

    # Zehner trennen a von b/c; Innenzehner fehlen → b und c bleiben gleich, nicht auflösbar.
    assert [(p.id, p.place, p.tied, p.tie_unresolved) for p in placements] == [
        ("a", 1, False, False),
        ("b", 2, True, True),
        ("c", 2, True, True),
    ]


def test_tie_with_partly_missing_tens_stays_unresolved() -> None:
    known = contender(PRAEZISION, raw({"shots": S1}, {"shots": S2}), "einzeln")
    unknown = contender(PRAEZISION, raw({"sum": 92}, {"sum": 76}), "summe", "series")

    placements = rank([known, unknown])

    assert [(p.place, p.tie_unresolved) for p in placements] == [(1, True), (1, True)]
