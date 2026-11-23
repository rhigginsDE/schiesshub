"""Abgebrochene Starts (DNS, DNF, DSQ) bekommen nie einen Platz und stehen nie vor Gewerteten.

Befund aus dem Audit: Ein aufgegebener Start (Fallscheibe, niedriger ist besser) mit
unvollständiger, kleinster Summe stand als „1.“ auf der Siegerliste.
"""

from typing import Any

import pytest

from app.scoring import Contender, RankPolicy, best_of, rank


def c(ident: str, *key: int | None, **extra: Any) -> Contender:
    return Contender(id=ident, key=list(key), **extra)


def places(placements: list) -> list[tuple]:
    return [(p.id, p.place, p.group) for p in placements]


def test_dnf_with_better_partial_time_never_gets_a_place() -> None:
    # Zeitwertung: Schlüssel ist die negierte Zeit; 40,00 s (2 von 4 Serien) wäre „besser“.
    contenders = [
        c("fertig", -4800),
        c("aufgegeben", -4000, complete=False, abort_reason="dnf"),
    ]
    assert places(rank(contenders)) == [
        ("fertig", 1, "ranked"),
        ("aufgegeben", None, "unranked"),
    ]


def test_dnf_alone_in_its_class_is_not_first() -> None:
    assert places(rank([c("allein", -4000, complete=False, abort_reason="dnf")])) == [
        ("allein", None, "unranked")
    ]


def test_ring_scoring_dnf_with_higher_partial_is_not_placed() -> None:
    # Ringwertung (höher ist besser): Auch wenn ein Teilergebnis vorn wäre, kein Platz.
    contenders = [c("fertig", 9000), c("aufgegeben", 9900, abort_reason="dnf")]
    assert places(rank(contenders)) == [("fertig", 1, "ranked"), ("aufgegeben", None, "unranked")]


def test_default_lists_every_abort_at_the_end_in_fixed_order() -> None:
    contenders = [
        Contender(id="disq", abort_reason="dsq"),
        Contender(id="nicht_da", abort_reason="dns"),
        c("aufgegeben", 50, abort_reason="dnf"),
        c("fertig", 10),
    ]
    assert places(rank(contenders)) == [
        ("fertig", 1, "ranked"),
        ("aufgegeben", None, "unranked"),
        ("nicht_da", None, "unranked"),
        ("disq", None, "unranked"),
    ]


def test_aborted_can_be_left_out() -> None:
    contenders = [c("fertig", 10), c("aufgegeben", 50, abort_reason="dnf")]
    policy = RankPolicy.for_list(final=True, include_aborted=False)
    assert places(rank(contenders, policy)) == [("fertig", 1, "ranked")]


def test_aborted_policy_cannot_grant_a_place() -> None:
    for value in ("normal", "last"):
        with pytest.raises(ValueError, match="dnf"):
            RankPolicy(dnf=value)  # type: ignore[arg-type]


def test_final_list_does_not_place_incomplete_results() -> None:
    contenders = [c("fertig", -4800), c("offen", -2000, complete=False)]
    assert places(rank(contenders, RankPolicy.for_list(final=True))) == [
        ("fertig", 1, "ranked"),
        ("offen", None, "unranked"),
    ]
    # Live: unvollständig hinten, aber nie vor den Vollständigen.
    assert places(rank(contenders, RankPolicy.for_list(final=False))) == [
        ("fertig", 1, "ranked"),
        ("offen", 2, "last"),
    ]


def test_best_of_never_prefers_an_aborted_attempt() -> None:
    attempts = [
        c("dieter-1", -4000, entry_id="dieter", attempt=1, complete=False, abort_reason="dnf"),
        c("dieter-2", -4800, entry_id="dieter", attempt=2),
    ]
    assert [s.id for s in best_of(attempts, "best")] == ["dieter-2"]
    assert [s.id for s in best_of(attempts, "first")] == ["dieter-2"]
    policy = RankPolicy.for_list(final=True)
    assert [s.id for s in best_of(attempts, "best", policy)] == ["dieter-2"]


def test_person_with_only_aborted_attempts_stands_at_the_end() -> None:
    starts = [
        c("anna-1", 9000, entry_id="anna"),
        c("ben-1", 9500, entry_id="ben", attempt=1, abort_reason="dnf"),
        Contender(id="ben-2", entry_id="ben", attempt=2, abort_reason="dns"),
    ]
    chosen = best_of(starts, "best")
    assert places(rank(chosen)) == [("anna-1", 1, "ranked"), ("ben-1", None, "unranked")]
    left_out = RankPolicy.for_list(final=True, include_aborted=False)
    assert places(rank(best_of(starts, "best", left_out), left_out)) == [("anna-1", 1, "ranked")]


# --- Abbruch nach „Feuer“ (Sporthandbuch K 1.14 / L 1.12) ---------------------------------


def test_abort_with_comparable_result_is_placed_normally() -> None:
    # Zeitwertung: 250 s (Abbruch, nicht geschossene Serien nach Regel) gegen 159 s.
    contenders = [
        c("aufgegeben", -25000, abort_reason="dnf", abort_ranked=True, complete=False),
        c("regulaer", -15900),
        c("langsam", -30000),
    ]
    assert places(rank(contenders, RankPolicy.for_list(final=True))) == [
        ("regulaer", 1, "ranked"),
        ("aufgegeben", 2, "ranked"),
        ("langsam", 3, "ranked"),
    ]


def test_placed_abort_stays_when_aborted_are_left_out() -> None:
    contenders = [
        c("aufgegeben", 90, abort_reason="dnf", abort_ranked=True),
        c("probe", 0, abort_reason="dnf"),
        Contender(id="nicht_da", abort_reason="dns"),
        c("fertig", 80),
    ]
    policy = RankPolicy.for_list(final=True, include_aborted=False)
    assert places(rank(contenders, policy)) == [
        ("aufgegeben", 1, "ranked"),
        ("fertig", 2, "ranked"),
    ]


def test_abort_ranked_only_for_dnf() -> None:
    contenders = [c("disq", 99, abort_reason="dsq", abort_ranked=True), c("fertig", 10)]
    assert places(rank(contenders)) == [("fertig", 1, "ranked"), ("disq", None, "unranked")]


def test_best_of_treats_placed_abort_like_a_result() -> None:
    attempts = [
        c("dieter-1", 95, entry_id="dieter", attempt=1, abort_reason="dnf", abort_ranked=True),
        c("dieter-2", 90, entry_id="dieter", attempt=2),
    ]
    assert [s.id for s in best_of(attempts, "best")] == ["dieter-1"]
    assert [s.id for s in best_of(attempts, "first")] == ["dieter-1"]
    worse = [
        c("eva-1", 80, entry_id="eva", attempt=1, abort_reason="dnf", abort_ranked=True),
        c("eva-2", 90, entry_id="eva", attempt=2),
    ]
    assert [s.id for s in best_of(worse, "best")] == ["eva-2"]
    assert [s.id for s in best_of(worse, "first")] == ["eva-1"]
