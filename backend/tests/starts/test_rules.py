"""Reine Regeln: Statusmaschine, Beträge, Mehrfachstart, Startnummern, Reihenfolge, Zeitplan."""

import itertools
import uuid
from datetime import UTC, datetime

import pytest

from app.modules.starts.rules import (
    START_STATUSES,
    TRANSITIONS,
    RuleError,
    Waiting,
    check_start_limit,
    check_transition,
    first_free_lane,
    first_start_number,
    has_result,
    heat_series,
    move_to,
    next_free_number,
    overlaps,
    pick_for_lanes,
    start_fee,
)

# --- Statusmaschine ----------------------------------------------------------

ALLOWED = {
    ("registered", "called"),
    ("registered", "aborted"),
    ("called", "registered"),
    ("called", "captured"),
    ("called", "aborted"),
    ("captured", "final"),
    ("captured", "aborted"),
    ("final", "captured"),
}


def test_transition_table_is_exactly_the_documented_one() -> None:
    table = {(source, target) for source, targets in TRANSITIONS.items() for target in targets}
    assert table == ALLOWED
    assert set(TRANSITIONS) == set(START_STATUSES)


@pytest.mark.parametrize(("current", "to"), sorted(itertools.product(START_STATUSES, repeat=2)))
def test_every_pair_is_allowed_or_rejected(current: str, to: str) -> None:
    kwargs = {"abort_reason": "dns"} if to == "aborted" else {}
    if (current, to) == ("final", "captured"):
        kwargs["reason"] = "Schreibfehler"
    if (current, to) in ALLOWED:
        check_transition(current, to, **kwargs)  # type: ignore[arg-type]
    else:
        with pytest.raises(RuleError, match="kann nicht"):
            check_transition(current, to, **kwargs)  # type: ignore[arg-type]


def test_abort_needs_reason_and_only_abort_takes_one() -> None:
    with pytest.raises(RuleError, match="Grund"):
        check_transition("called", "aborted")
    with pytest.raises(RuleError, match="Abbruchgrund"):
        check_transition("registered", "called", abort_reason="dns")


def test_reopening_needs_a_reason() -> None:
    with pytest.raises(RuleError, match="Wiederöffnen"):
        check_transition("final", "captured")
    with pytest.raises(RuleError, match="Wiederöffnen"):
        check_transition("final", "captured", reason="  ")
    check_transition("final", "captured", reason="Ringzahl falsch übertragen")


def test_has_result() -> None:
    assert not has_result("registered", None)
    assert not has_result("aborted", "dns")
    assert has_result("called", None)
    assert has_result("captured", None)
    assert has_result("final", None)
    assert has_result("aborted", "dnf")
    assert has_result("aborted", "dsq")


# --- Startgeld und Mehrfachstart ---------------------------------------------


def test_fee_first_then_repeat() -> None:
    assert [start_fee(attempt, 1500, 800) for attempt in (1, 2, 3)] == [1500, 800, 800]
    with pytest.raises(ValueError, match="attempt"):
        start_fee(0, 1500, 800)


def test_single_start_only() -> None:
    check_start_limit(False, 1, 0, 1)
    with pytest.raises(RuleError, match="nur ein Start"):
        check_start_limit(False, 1, 1, 1)
    with pytest.raises(RuleError, match="nur ein Start"):
        check_start_limit(False, 1, 0, 2)


def test_multi_start_names_the_maximum() -> None:
    check_start_limit(True, 3, 1, 2)
    with pytest.raises(RuleError, match=r"höchstens 3 Starts .* gebucht sind schon 2"):
        check_start_limit(True, 3, 2, 2)
    with pytest.raises(RuleError, match=r"höchstens 3 Starts .* gebucht ist schon 1"):
        check_start_limit(True, 3, 1, 3)


# --- Startnummern ------------------------------------------------------------


def test_next_free_number_fills_gaps_from_start_value() -> None:
    assert next_free_number([], 1) == 1
    assert next_free_number([1, 2, 4], 1) == 3
    assert next_free_number([100, 101, 5], 100) == 102
    assert next_free_number([1, 2, 3], 50) == 50


def test_first_start_number_from_settings() -> None:
    assert first_start_number({}) == 1
    assert first_start_number({"first_start_number": 100}) == 100
    assert first_start_number({"first_start_number": 0}) == 1
    assert first_start_number({"first_start_number": True}) == 1
    assert first_start_number({"first_start_number": "7"}) == 1


# --- Reihenfolge -------------------------------------------------------------


def test_move_to() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert move_to([a, b, c], c, 1) == [c, a, b]
    assert move_to([a, b, c], a, 3) == [b, c, a]
    assert move_to([a, b, c], b, 2) == [a, b, c]
    with pytest.raises(RuleError, match="zwischen 1 und 3"):
        move_to([a, b, c], a, 4)
    with pytest.raises(RuleError, match="wartet nicht"):
        move_to([a, b], c, 1)


def test_pick_for_lanes_skips_busy_and_doubled_persons() -> None:
    s1, s2, s3, s4 = (uuid.uuid4() for _ in range(4))
    anna, ben, carl = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    waiting = [Waiting(s1, anna), Waiting(s2, anna), Waiting(s3, ben), Waiting(s4, carl)]
    # Anna kommt einmal dran, ihr zweiter Start wartet; Carl ist schon auf einer Bahn.
    assert pick_for_lanes([1, 3, 4], waiting, busy_entries={carl}) == [(s1, 1), (s3, 3)]
    assert pick_for_lanes([2], waiting, busy_entries=set()) == [(s1, 2)]
    assert pick_for_lanes([], waiting, busy_entries=set()) == []


def test_first_free_lane() -> None:
    assert first_free_lane(3, [1, 3]) == 2
    assert first_free_lane(2, [1, 2]) is None


# --- Zeitplan ----------------------------------------------------------------


def test_heat_series_back_to_back() -> None:
    first = datetime(2027, 3, 6, 9, 0, tzinfo=UTC)
    series = heat_series(first, 3, 25)
    assert [(s.strftime("%H:%M"), e.strftime("%H:%M")) for s, e in series] == [
        ("09:00", "09:25"),
        ("09:25", "09:50"),
        ("09:50", "10:15"),
    ]


def test_overlaps_is_half_open() -> None:
    def t(minute: int) -> datetime:
        return datetime(2027, 3, 6, 9, minute, tzinfo=UTC)

    assert overlaps(t(0), t(30), t(15), t(45))
    assert overlaps(t(0), t(30), t(5), t(10))
    assert not overlaps(t(0), t(30), t(30), t(45))
    assert not overlaps(t(30), t(45), t(0), t(30))
