"""Reine Regeln: Ereignisse falten, Unterschiede der Rohwerte, Prüfgründe beim Werten."""

from datetime import UTC, datetime, timedelta

from app.modules.ergebnisse.rules import (
    EventRecord,
    RawChange,
    evaluate,
    raw_changes,
    replay,
    request_hash,
)
from tests.ergebnisse.conftest import precision_definition, shots

T0 = datetime(2027, 3, 6, 9, 0, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def test_replay_follows_sequence_not_list_order() -> None:
    until = at(31).isoformat()
    events = [
        EventRecord(3, "reopened", {}, at(10)),
        EventRecord(1, "raw_set", {"raw": shots([9])}, at(0)),
        EventRecord(2, "finalized", {"provisional_until": None}, at(1)),
        EventRecord(4, "raw_set", {"raw": shots([10])}, at(11)),
        EventRecord(5, "finalized", {"provisional_until": None}, at(12)),
        EventRecord(6, "corrected", {"raw": shots([8]), "provisional_until": until}, at(30)),
    ]
    state = replay(events)
    assert state.raw == shots([8])
    assert state.last_seq == 6
    assert state.is_final
    assert state.finalized_at == at(30)
    assert state.provisional_until == at(31)

    reopened = replay(events[:4])
    assert reopened.raw == shots([10])
    assert not reopened.is_final
    assert reopened.finalized_at is None
    assert reopened.provisional_until is None


def test_replay_abort_keeps_raw() -> None:
    state = replay(
        [
            EventRecord(1, "raw_set", {"raw": shots([9, 9])}, at(0)),
            EventRecord(2, "aborted", {"abort_reason": "dnf"}, at(2)),
        ]
    )
    assert state.raw == shots([9, 9])
    assert not state.is_final
    assert state.last_seq == 2


def test_raw_changes() -> None:
    before = {"sections": {"s": {"series": [{"shots": [9, 9]}, {"time_cs": 100, "standing": 1}]}}}
    after = {"sections": {"s": {"series": [{"shots": [9, 10]}, {"time_cs": 100}, {"sum": 3}]}}}
    assert raw_changes(before, after) == [
        RawChange("sections.s.series[0].shots", [9, 9], [9, 10]),
        RawChange("sections.s.series[1].standing", 1, None),
        RawChange("sections.s.series[2].sum", None, 3),
    ]
    many = {"sections": {"s": {"series": [{"sum": n} for n in range(11)]}}}
    assert [c.path for c in raw_changes({}, many)][-2:] == [
        "sections.s.series[9].sum",
        "sections.s.series[10].sum",
    ]


def test_request_hash_depends_on_action_and_body() -> None:
    body = {"raw": shots([9]), "base_seq": 0}
    assert request_hash("raw_set", body) == request_hash("raw_set", dict(reversed(body.items())))
    assert request_hash("raw_set", body) != request_hash("corrected", body)


def test_evaluate_marks_incomplete_final_and_unfit_raw() -> None:
    definition = precision_definition(series=2)
    ok = evaluate(definition, "shot", shots([10] * 5, [9] * 5), is_final=True)
    assert ok.review_reason is None
    assert ok.score == 95
    assert ok.rank_keys == [9500, 5, 0]

    open_partial = evaluate(definition, "shot", shots([10] * 5), is_final=False)
    assert open_partial.review_reason is None

    final_partial = evaluate(definition, "shot", shots([10] * 5), is_final=True)
    assert final_partial.computed is not None
    assert final_partial.review_reason is not None
    assert "Serie 2 fehlt" in final_partial.review_reason

    unfit = evaluate(definition, "shot", shots([10] * 5, [9] * 5, [8] * 5), is_final=True)
    assert unfit.computed is None
    assert unfit.rank_keys is None
    assert unfit.review_reason is not None
    assert "passen nicht" in unfit.review_reason

    broken = evaluate({"variant": {}, "scoring": {}}, "shot", {}, is_final=False)
    assert broken.computed is None
    assert broken.review_reason is not None
