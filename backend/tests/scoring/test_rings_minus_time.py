"""Modell `ringe_minus_zeit` (Speed), handgerechnet.

Serien: 10+10+7+10+0 = 37 in 8,53 s · 5×10 = 50 in 10,21 s · 7+7+10+10+10 = 44 in 11,66 s ·
10+0+10+7+10 = 37 in 9,99 s → 168 Ringe, 40,39 s.
"""

from decimal import Decimal

from app.scoring import Issue, compute, describe_form, rank, validate_raw
from tests.scoring import definitions
from tests.scoring.support import contender, series_of

KW_SPEED = definitions.speed()  # zeit_rundung: summe_abrunden
FLINTE_SPEED = definitions.speed(rounding=False)

SERIES = [
    {"shots": [10, 10, 7, 10, 0], "time_cs": 853},
    {"shots": [10, 10, 10, 10, 10], "time_cs": 1021},
    {"shots": [7, 7, 10, 10, 10], "time_cs": 1166},
    {"shots": [10, 0, 10, 7, 10], "time_cs": 999},
]


def raw(*series: dict) -> dict:
    return series_of(*series, section="speed")


def test_sum_of_times_is_rounded_down_before_subtracting() -> None:
    result = compute(KW_SPEED, "shot", raw(*SERIES))

    assert result.score == Decimal(128)  # 168 − ⌊40,39⌋
    assert result.score_text == "128 Punkte"
    assert result.complete
    assert result.time_cs == 4039
    assert result.steps == [
        "Serie 1: 10 + 10 + 7 + 10 + 0 = 37 Ringe, Zeit 8,53 s",
        "Serie 2: 10 + 10 + 10 + 10 + 10 = 50 Ringe, Zeit 10,21 s",
        "Serie 3: 7 + 7 + 10 + 10 + 10 = 44 Ringe, Zeit 11,66 s",
        "Serie 4: 10 + 0 + 10 + 7 + 10 = 37 Ringe, Zeit 9,99 s",
        "Ringe: 37 + 50 + 44 + 37 = 168",
        "Zeit: 8,53 s + 10,21 s + 11,66 s + 9,99 s = 40,39 s",
        "Zeitsumme auf volle Sekunden abgerundet: 40 s",
        "Ergebnis: 168 − 40 = 128 Punkte",
    ]


def test_without_rounding_rule_time_is_subtracted_exactly() -> None:
    result = compute(FLINTE_SPEED, "shot", raw(*SERIES))

    assert result.score == Decimal("127.61")
    assert result.steps[-1] == "Ergebnis: 168 − 40,39 = 127,61 Punkte"


def test_rounding_applies_to_the_sum_not_each_series() -> None:
    # Je Serie abgerundet wären es 4 × 9 = 36 s, die Summe 39,96 s ergibt 39 s.
    series = [{"shots": [10] * 5, "time_cs": 999}] * 4
    assert compute(KW_SPEED, "shot", raw(*series)).score == Decimal(200 - 39)


def test_negative_result_is_not_limited() -> None:
    series = [{"shots": [0] * 5, "time_cs": 5999}] * 4  # 239,96 s

    result = compute(KW_SPEED, "shot", raw(*series))

    assert result.score == Decimal(-239)
    assert result.score_text == "−239 Punkte"


def test_time_over_limit_is_counted_unchanged_with_warning() -> None:
    series = [*SERIES[:3], {"shots": [10, 0, 10, 7, 10], "time_cs": 6150}]

    result = compute(KW_SPEED, "shot", raw(*series))

    assert result.score == Decimal(168 - 91)  # 8,53 + 10,21 + 11,66 + 61,50 = 91,90 s
    assert result.time_cs == 853 + 1021 + 1166 + 6150
    assert [w.path for w in result.warnings] == ["sections.speed.series[3].time_cs"]
    assert result.warnings[0].message.startswith(
        "Serie 4: 61,50 s liegt über dem Zeitlimit von 60 s."
    )


def test_series_needs_time_to_be_complete() -> None:
    incomplete = raw(*SERIES[:3], {"shots": [10, 0, 10, 7, 10]})

    assert validate_raw(KW_SPEED, "shot", incomplete, partial=False) == [
        Issue(path="sections.speed.series[3].time_cs", message="Serie 4: Zeit fehlt")
    ]
    result = compute(KW_SPEED, "shot", incomplete)
    assert not result.complete
    assert result.score == Decimal(168 - 30)  # 30,40 s bisher


def test_invalid_times() -> None:
    for value in (0, -5, 12.84, "1284", True):
        issues = validate_raw(KW_SPEED, "shot", raw({"shots": [10] * 5, "time_cs": value}))
        assert issues == [
            Issue(
                path="sections.speed.series[0].time_cs",
                message="Serie 1: Zeit: in Hundertstelsekunden als ganze Zahl größer 0",
            )
        ], value


def test_form_has_rings_and_time_per_series() -> None:
    form = describe_form(KW_SPEED, "shot")
    series = form.sections[0].series[0]

    assert [f.key for f in series.fields] == ["shots", "time_cs"]
    assert series.max_time_s == Decimal(60)
    assert series.hints == ["5 Schuss", "5 Scheiben", "Zeitlimit 60 s"]
    assert form.max_rings == 200
    assert form.direction == "absteigend"
    assert describe_form(KW_SPEED, "series").sections[0].series[0].fields[0].key == "sum"


def test_ranking_higher_is_better_and_ties_share_place() -> None:
    fast = contender(KW_SPEED, raw(*SERIES), "schnell")  # 128
    same = contender(KW_SPEED, raw(*reversed(SERIES)), "gleich")  # 128
    slow = contender(
        KW_SPEED, raw(*[{**s, "time_cs": s["time_cs"] + 100} for s in SERIES]), "langsam"
    )  # 168 − 44 = 124

    placements = rank([slow, same, fast])

    assert [(p.id, p.place, p.tied) for p in placements] == [
        ("gleich", 1, True),
        ("schnell", 1, True),
        ("langsam", 3, False),
    ]
