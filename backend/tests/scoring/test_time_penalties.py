"""Modell `zeit_plus_zuschlaege` (Fallscheibe), handgerechnet an KW 25 m Fallscheibe GK (BM/LM).

12,84 s + 1 × 10 s = 22,84 s · 9,90 s · 58,10 s + 2 × 10 s = 78,10 s · 15,00 s → 125,84 s.
"""

from decimal import Decimal

from app.scoring import Issue, compute, describe_form, rank, validate_raw
from tests.scoring import definitions
from tests.scoring.support import contender, series_of

GK = definitions.fallscheibe()
GK_DM = definitions.fallscheibe(6)

SERIES = [
    {"time_cs": 1284, "standing": 1},
    {"time_cs": 990, "standing": 0},
    {"time_cs": 5810, "standing": 2},
    {"time_cs": 1500, "standing": 0},
]


def raw(*series: dict | None) -> dict:
    return series_of(*series, section="fallscheibe")


def test_time_plus_penalties_hand_computed() -> None:
    result = compute(GK, "shot", raw(*SERIES))

    assert result.score == Decimal("125.84")
    assert result.score_text == "125,84 s"
    assert result.complete
    assert (result.time_cs, result.penalty_cs, result.rings) == (9584, 3000, None)
    assert [s.total_cs for s in result.sections[0].series] == [2284, 990, 7810, 1500]
    assert result.steps == [
        "Serie 1: 12,84 s + 1 stehende Scheibe × 10 s = 22,84 s",
        "Serie 2: 9,90 s + 0 stehende Scheiben × 10 s = 9,90 s",
        "Serie 3: 58,10 s + 2 stehende Scheiben × 10 s = 78,10 s",
        "Serie 4: 15,00 s + 0 stehende Scheiben × 10 s = 15,00 s",
        "Ergebnis: 22,84 s + 9,90 s + 78,10 s + 15,00 s = 125,84 s",
    ]
    assert result.warnings == []


def test_time_over_series_limit_is_not_capped_only_warned() -> None:
    series = [*SERIES[:3], {"time_cs": 6120, "standing": 0}]

    result = compute(GK, "shot", raw(*series))

    assert result.score == Decimal("172.04")  # 61,20 s gehen unverändert ein
    assert result.warnings == [
        Issue(
            path="sections.fallscheibe.series[3].time_cs",
            message="Serie 4: 61,20 s liegt über dem Zeitlimit von 60 s. Der Katalog legt dafür "
            "keine Wertung fest; die Zeit geht unverändert ein – bitte nach Regelwerk prüfen.",
        )
    ]
    assert validate_raw(GK, "shot", raw(*series), partial=False) == []


def test_standing_targets_are_limited_by_targets_per_series() -> None:
    issues = validate_raw(GK, "shot", raw(*SERIES[:2], {"time_cs": 1000, "standing": 6}))
    assert issues == [
        Issue(
            path="sections.fallscheibe.series[2].standing",
            message="Serie 3: höchstens 5 stehende Scheiben",
        )
    ]
    assert validate_raw(GK, "shot", raw({"time_cs": 1000, "standing": -1})) == [
        Issue(
            path="sections.fallscheibe.series[0].standing",
            message="Serie 1: stehende Scheiben als ganze Zahl ab 0",
        )
    ]


def test_rings_are_not_part_of_fallscheibe() -> None:
    assert validate_raw(GK, "shot", raw({"time_cs": 1000, "standing": 0, "shots": [10]})) == [
        Issue(
            path="sections.fallscheibe.series[0].shots",
            message="Serie 1: dieser Abschnitt wertet keine Ringe",
        )
    ]


def test_partial_series() -> None:
    result = compute(GK, "shot", raw(SERIES[0], {"time_cs": 990}, None, {"standing": 1}))

    assert not result.complete
    assert result.score == Decimal("42.74")  # 22,84 + 9,90 + 10,00
    assert result.progress.series_complete == 1
    assert result.steps[1:3] == [
        "Serie 2: 9,90 s (stehende Scheiben noch nicht erfasst)",
        "Serie 4: Zeit noch nicht erfasst, 1 stehende Scheibe × 10 s = 10,00 s",
    ]
    assert validate_raw(GK, "shot", raw(SERIES[0], {"time_cs": 990}), partial=False) == [
        Issue(
            path="sections.fallscheibe.series[1].standing",
            message="Serie 2: Anzahl stehender Scheiben fehlt",
        ),
        Issue(path="sections.fallscheibe.series[2]", message="Serie 3 fehlt"),
        Issue(path="sections.fallscheibe.series[3]", message="Serie 4 fehlt"),
    ]


def test_form_and_capture_mode_make_no_difference() -> None:
    shot, series = describe_form(GK, "shot"), describe_form(GK, "series")

    assert shot.sections == series.sections
    first = shot.sections[0].series[0]
    assert [(f.key, f.kind, f.min, f.max) for f in first.fields] == [
        ("time_cs", "time", 1, None),
        ("standing", "integer", 0, 5),
    ]
    assert first.hints == [
        "höchstens 16 Schuss",
        "5 Scheiben",
        "Zeitlimit 60 s",
        "10 s Zuschlag je stehender Scheibe",
    ]
    assert shot.max_rings is None
    assert shot.direction == "aufsteigend"
    assert shot.tie_breakers == []
    assert len(describe_form(GK_DM, "shot").sections[0].series) == 6


def test_lower_time_ranks_first_and_ties_share_place() -> None:
    fast = contender(GK, raw(*SERIES), "schnell")  # 125,84
    same = contender(GK, raw(*reversed(SERIES)), "gleich")  # 125,84
    slower = contender(GK, raw(*SERIES[:3], {"time_cs": 1501, "standing": 0}), "langsamer")
    penalty = contender(GK, raw(*SERIES[:3], {"time_cs": 600, "standing": 1}), "zuschlag")  # 126,84

    placements = rank([penalty, slower, fast, same])

    assert [(p.id, p.place, p.tied, p.tie_unresolved) for p in placements] == [
        ("schnell", 1, True, False),
        ("gleich", 1, True, False),
        ("langsamer", 3, False, False),
        ("zuschlag", 4, False, False),
    ]
    assert fast.key == [-12584]
