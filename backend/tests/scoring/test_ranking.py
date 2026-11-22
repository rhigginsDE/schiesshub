"""Rangliste: Schlüssel, geteilte Plätze, unvollständige/abgebrochene Starts, Mehrfachstart."""

import copy
from typing import Any

import pytest

from app.scoring import Contender, RankPolicy, best_of, compute, rank, rank_key
from tests.scoring import definitions

MEHRDISTANZ = definitions.mehrdistanz_kw()


def c(ident: str, *key: int | None, **extra: Any) -> Contender:
    return Contender(id=ident, key=list(key), **extra)


def places(placements: list) -> list[tuple]:
    return [(p.id, p.place, p.group) for p in placements]


def test_rank_key_covers_every_tie_breaker() -> None:
    data = copy.deepcopy(MEHRDISTANZ)
    data["scoring"]["gleichstand"] = ["parcours_zeit", "neuner_abwaerts", "innenzehner", "zehner"]
    raw = {
        "sections": {
            "fertigkeit": {"series": [{"shots": ["X", 10, 9, 8, 1]}]},
            "parcours": {"series": [{"shots": [9, 9, 7, 2, 0]}], "time_cs": 7000},
        }
    }

    key = rank_key(data, compute(data, "shot", raw))

    #       Ergebnis·100  −Parcourszeit  9  8  7  6  5  4  3  2  1  Innenzehner  Zehner
    assert key == [6500, -7000, 3, 1, 1, 0, 0, 0, 0, 1, 1, 1, 2]


def test_rank_key_rejects_result_of_other_model() -> None:
    result = compute(definitions.praezision(), "shot", {})
    with pytest.raises(ValueError, match="Modell „ringe“"):
        rank_key(MEHRDISTANZ, result)


def test_competition_ranking_1_2_2_4() -> None:
    placements = rank([c("d", 80), c("b", 90), c("a", 100), c("c", 90)])
    assert [(p.id, p.place, p.tied) for p in placements] == [
        ("a", 1, False),
        ("b", 2, True),
        ("c", 2, True),
        ("d", 4, False),
    ]


def test_tie_breakers_are_applied_in_order() -> None:
    placements = rank([c("a", 90, 3, 0), c("b", 90, 3, 1), c("c", 90, 4, 0), c("d", 90, 3, 1)])
    assert [(p.id, p.place, p.tied) for p in placements] == [
        ("c", 1, False),
        ("b", 2, True),
        ("d", 2, True),
        ("a", 4, False),
    ]


def test_missing_value_stops_tie_breaking_for_that_group_only() -> None:
    placements = rank([c("a", 90, 3, None), c("b", 90, 3, 1), c("c", 80, 2, 1), c("d", 80, 2, 0)])
    assert [(p.id, p.place, p.tied, p.tie_unresolved) for p in placements] == [
        ("a", 1, True, True),
        ("b", 1, True, True),
        ("c", 3, False, False),
        ("d", 4, False, False),
    ]


def test_default_policy_puts_incomplete_last_and_aborted_unranked() -> None:
    contenders = [
        c("fertig", 90),
        c("offen", 95, complete=False),
        c("aufgegeben", 99, complete=False, abort_reason="dnf"),
        c("nicht_da", None, abort_reason="dns"),
        Contender(id="disq", abort_reason="dsq"),
        c("besser", 92),
    ]

    assert places(rank(contenders)) == [
        ("besser", 1, "ranked"),
        ("fertig", 2, "ranked"),
        ("offen", 3, "last"),
        ("aufgegeben", None, "unranked"),
        ("nicht_da", None, "unranked"),
        ("disq", None, "unranked"),
    ]


def test_policy_options() -> None:
    contenders = [
        c("fertig", 90),
        c("offen", 95, complete=False),
        c("aufgegeben", 99, complete=False, abort_reason="dnf"),
        Contender(id="nicht_da", abort_reason="dns"),
        c("disq", 100, abort_reason="dsq"),
    ]
    policy = RankPolicy(incomplete="exclude", dnf="unranked", dns="unranked", dsq="exclude")

    assert places(rank(contenders, policy)) == [
        ("fertig", 1, "ranked"),
        ("aufgegeben", None, "unranked"),
        ("nicht_da", None, "unranked"),
    ]
    live = RankPolicy(incomplete="normal", dnf="exclude", dns="exclude", dsq="exclude")
    assert places(rank(contenders, live)) == [("offen", 1, "ranked"), ("fertig", 2, "ranked")]


def test_ranked_contender_needs_a_key() -> None:
    with pytest.raises(ValueError, match="Start x: Vergleichsschlüssel fehlt"):
        rank([Contender(id="x")])
    with pytest.raises(ValueError, match="unterschiedlich lang"):
        rank([c("a", 1), c("b", 1, 2)])


def test_best_of_rules() -> None:
    starts = [
        c("anna-1", 85, entry_id="anna", attempt=1),
        c("anna-2", 92, entry_id="anna", attempt=2),
        c("anna-3", 92, entry_id="anna", attempt=3),
        c("ben-1", None, entry_id="ben", attempt=1, abort_reason="dns"),
        c("ben-2", 70, entry_id="ben", attempt=2),
        c("cem-2", 99, entry_id="cem", attempt=2, complete=False),
        c("cem-1", 60, entry_id="cem", attempt=1),
    ]

    assert [s.id for s in best_of(starts, "best")] == ["anna-2", "ben-2", "cem-1"]
    assert [s.id for s in best_of(starts, "first")] == ["anna-1", "ben-2", "cem-1"]
    assert best_of(starts, "all") == starts
    # Wer unvollständige Starts regulär wertet, bekommt den besseren Teilstand.
    live = RankPolicy(incomplete="normal")
    assert [s.id for s in best_of(starts, "best", live)] == ["anna-2", "ben-2", "cem-2"]


def test_best_of_with_only_aborted_starts() -> None:
    starts = [
        Contender(id="a1", entry_id="a", attempt=1, abort_reason="dns"),
        c("a2", 50, entry_id="a", attempt=2, abort_reason="dsq"),
    ]
    assert [s.id for s in best_of(starts, "first")] == ["a2"]
    assert [s.id for s in best_of(starts, "best")] == ["a1"]  # beide ohne Wertung → der frühere


def test_best_of_rejects_unknown_rule() -> None:
    with pytest.raises(ValueError, match="Mehrfachstart-Regel „zweitbester“"):
        best_of([], "zweitbester")  # type: ignore[arg-type]


def test_rank_after_best_of() -> None:
    starts = [
        c("anna-1", 85, entry_id="anna", attempt=1),
        c("anna-2", 92, entry_id="anna", attempt=2),
        c("ben-1", 90, entry_id="ben", attempt=1),
    ]
    assert [(p.id, p.place) for p in rank(best_of(starts, "best"))] == [("anna-2", 1), ("ben-1", 2)]
    assert [(p.id, p.place) for p in rank(best_of(starts, "all"))] == [
        ("anna-2", 1),
        ("ben-1", 2),
        ("anna-1", 3),
    ]
