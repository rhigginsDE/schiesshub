"""Wertung eines Abbruchs durch den Schützen (`compute_aborted`).

Sporthandbuch K 1.14 / L 1.12: Wer nach dem Kommando „Feuer“ abbricht, wird nach dem bis dahin
erzielten Ergebnis platziert. Nicht geschossene Serien zählen so, wie die Definition es für eine
abgebrochene Serie vorsieht; fehlt dafür eine Regel, ist das Ergebnis nicht vergleichbar.
"""

from decimal import Decimal

from app.scoring import Contender, compute, compute_aborted, rank, rank_key
from tests.scoring import definitions
from tests.scoring.support import series_of


def fallscheibe_mit_abbruch(serien: int = 4) -> dict:
    """Wie Flinte 15 m Fallscheibe (4401): 4 Serien, 5 Scheiben, 10 s Zuschlag, Abbruch 60 s."""
    definition = definitions.fallscheibe(serien, max_schuss=6)
    section = definition["variant"]["abschnitte"][0]
    section["zeit_bei_abbruch_s"] = 60
    section["zuschlag_stoerung_vor_erstem_schuss_s"] = 50
    return definition


def test_qa_case_fallscheibe_unshot_series_count_as_aborted_by_shooter() -> None:
    """QA-Fall: 15 s + 15 s, dann aufgegeben – gegen einen regulären Start mit 159 s."""
    definition = fallscheibe_mit_abbruch()
    raw = series_of(
        {"time_cs": 1500, "standing": 0},
        {"time_cs": 1500, "standing": 0},
        section="fallscheibe",
    )
    outcome = compute_aborted(definition, "shot", raw)

    assert outcome.has_values
    assert outcome.reason is None
    assert outcome.computed is not None
    # Serie 3 und 4: 60 s + 5 stehende Scheiben × 10 s = 110 s je Serie.
    assert outcome.computed.score == Decimal("250.00")
    assert [s.total_cs for s in outcome.computed.sections[0].series] == [1500, 1500, 11000, 11000]
    assert [s.status for s in outcome.computed.sections[0].series] == [
        "normal",
        "normal",
        "aborted_by_shooter",
        "aborted_by_shooter",
    ]
    assert outcome.unshot == ["Serie 3", "Serie 4"]
    assert outcome.computed.steps[0].startswith("Abbruch (AB): Serie 3 und 4 nicht geschossen")

    regular = compute(
        definition,
        "shot",
        series_of(
            {"time_cs": 3900, "standing": 0},
            {"time_cs": 4000, "standing": 0},
            {"time_cs": 4000, "standing": 0},
            {"time_cs": 4000, "standing": 0},
            section="fallscheibe",
        ),
    )
    assert regular.score == Decimal("159.00")
    placements = rank(
        [
            Contender(
                id="aufgegeben",
                key=rank_key(definition, outcome.computed),
                abort_ranked=True,
                abort_reason="dnf",
            ),
            Contender(id="regulaer", key=rank_key(definition, regular)),
        ]
    )
    assert [(p.id, p.place) for p in placements] == [("regulaer", 1), ("aufgegeben", 2)]


def test_fallscheibe_without_abort_time_has_no_rule() -> None:
    definition = definitions.fallscheibe()  # ohne zeit_bei_abbruch_s
    raw = series_of({"time_cs": 1500, "standing": 0}, section="fallscheibe")
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.has_values
    assert outcome.computed is None
    assert outcome.reason == "no_rule"


def test_fallscheibe_partly_captured_series_is_not_comparable() -> None:
    definition = fallscheibe_mit_abbruch()
    raw = series_of({"time_cs": 1500, "standing": 0}, {"time_cs": 1700}, section="fallscheibe")
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is None
    assert outcome.reason == "incomplete_series"
    assert outcome.incomplete == ["Serie 2"]


def test_fallscheibe_series_marked_as_aborted_counts_as_captured() -> None:
    definition = fallscheibe_mit_abbruch()
    raw = series_of(
        {"time_cs": 1500, "standing": 0},
        {"status": "aborted_by_shooter", "standing": 2},
        section="fallscheibe",
    )
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is not None
    # 15 + (60 + 20) + 110 + 110
    assert outcome.computed.score == Decimal("315.00")


def test_no_values_is_abort_in_sighting() -> None:
    outcome = compute_aborted(fallscheibe_mit_abbruch(), "shot", {})
    assert not outcome.has_values
    assert outcome.computed is None
    assert outcome.reason is None


def test_rings_missing_shots_count_zero() -> None:
    """A 9.08: kein Nachholen – nicht abgegebene Schüsse zählen 0 Ringe."""
    definition = definitions.praezision()
    raw = series_of(
        {"shots": [10, 9, 9, 8, 10, "X", 7, 9, 10, 8]}, {"shots": [9, 9]}, section="praezision"
    )
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is not None
    assert outcome.computed.score == Decimal(108)
    assert outcome.computed.tens == 4
    assert "nicht abgegebene Schüsse zählen 0 Ringe" in outcome.computed.steps[0]


def test_rings_unshot_series_count_zero() -> None:
    definition = definitions.praezision()
    raw = series_of({"shots": [10] * 10}, section="praezision")
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is not None
    assert outcome.computed.score == Decimal(100)
    assert outcome.unshot == ["Serie 2"]


def test_rings_series_sum_counts() -> None:
    definition = definitions.praezision()
    raw = series_of({"sum": 92, "tens": 3, "inner_tens": 1}, section="praezision")
    outcome = compute_aborted(definition, "series", raw)
    assert outcome.computed is not None
    assert outcome.computed.score == Decimal(92)


def test_speed_unshot_series_has_no_rule() -> None:
    """Ringe minus Zeit: Für eine Serie ohne Schuss gibt es keine Zeit des letzten Schusses."""
    definition = definitions.speed()
    raw = series_of({"shots": [10, 10, 10, 10, 10], "time_cs": 500}, section="speed")
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is None
    assert outcome.reason == "no_rule"


def test_speed_all_series_captured_with_missing_shots_counts() -> None:
    definition = definitions.speed(serien=2)
    raw = series_of(
        {"shots": [10, 10, 10, 10, 10], "time_cs": 500},
        {"shots": [10, 7], "time_cs": 300},
        section="speed",
    )
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is not None
    assert outcome.computed.score == Decimal(67 - 8)


def test_speed_series_without_time_is_not_comparable() -> None:
    definition = definitions.speed(serien=2)
    raw = series_of(
        {"shots": [10, 10, 10, 10, 10], "time_cs": 500}, {"shots": [10, 7]}, section="speed"
    )
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is None
    assert outcome.reason == "incomplete_series"


def test_mehrdistanz_unshot_parcours_counts_zero_with_floor() -> None:
    definition = definitions.mehrdistanz_kw()
    raw = {"sections": {"fertigkeit": {"series": [{"shots": [10, 10, 9, 9, 8]}]}}}
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is not None
    assert outcome.computed.score == Decimal(46)


def test_mehrdistanz_parcours_shot_without_time_is_not_comparable() -> None:
    definition = definitions.mehrdistanz_kw()
    raw = {
        "sections": {
            "fertigkeit": {"series": [{"shots": [10] * 5}] * 4},
            "parcours": {"series": [{"shots": [10] * 5}]},
        }
    }
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is None
    assert outcome.reason == "missing_section_time"


def test_mehrdistanz_parcours_with_time_counts() -> None:
    definition = definitions.mehrdistanz_kw()
    raw = {
        "sections": {
            "fertigkeit": {"series": [{"shots": [10] * 5}] * 4},
            "parcours": {"series": [{"shots": [10] * 5}], "time_cs": 9000},
        }
    }
    outcome = compute_aborted(definition, "shot", raw)
    assert outcome.computed is not None
    # 200 + 50 − 10 (90 s bei Sollzeit 80 s)
    assert outcome.computed.score == Decimal(240)
