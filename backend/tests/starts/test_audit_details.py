"""Protokoll der Starts: Startnummer und Wettbewerb in jedem Eintrag, Bemerkung beim Abbruch."""

from collections.abc import Iterator
from typing import Any

import pytest

from app.modules.starts import hooks
from tests.starts.conftest import Api, Setup


async def _audit(api: Api) -> dict[str, list[dict[str, Any]]]:
    items = (await api.ok("GET", "/audit", params={"limit": 200}))["items"]
    by_action: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_action.setdefault(item["action"], []).append(item["details"])
    return by_action


async def test_booked_cancelled_and_released_name_the_start_number(
    api: Api, queue_setup: Setup
) -> None:
    setup = queue_setup
    tid = setup.tid
    await api.ok(
        "PATCH",
        f"/tournaments/{tid}/competitions/{setup.competition_id}",
        json={"multi_start": True, "max_starts": 3},
    )
    entry = await api.entry(tid, setup.class_id, start_number=17)
    first, second = await api.book(tid, entry["id"], setup.competition_id, count=2)
    await api.ok("DELETE", f"/tournaments/{tid}/starts/{second['id']}", 204)
    path = f"/tournaments/{tid}/starts/{first['id']}"
    await api.ok("POST", f"{path}/call", json={})
    raw = {"sections": {"lauf": {"series": [{"sum": 40}]}}}
    await api.ok("PUT", f"{path}/raw", json={"raw": raw, "base_seq": 0})
    await api.ok("POST", f"{path}/release-lane")

    audit = await _audit(api)
    (booked,) = audit["start.booked"]
    assert booked["start_number"] == 17
    assert booked["competition_name"] == "Fallscheibe"
    assert "competition_code" in booked
    assert booked["attempts"] == [1, 2]
    (cancelled,) = audit["start.cancelled"]
    assert (cancelled["start_number"], cancelled["attempt"]) == (17, 2)
    assert cancelled["competition_name"] == "Fallscheibe"
    (released,) = audit["start.lane_released"]
    assert (released["start_number"], released["attempt"], released["lane"]) == (17, 1, 1)
    assert released["competition_name"] == "Fallscheibe"
    assert released["range_id"] == setup.range_id
    assert "Muster" not in str(audit)


async def test_abort_note_lands_in_result_log_and_audit(api: Api, queue_setup: Setup) -> None:
    setup = queue_setup
    tid = setup.tid
    entry = await api.entry(tid, setup.class_id)
    (start,) = await api.book(tid, entry["id"], setup.competition_id)
    path = f"/tournaments/{tid}/starts/{start['id']}"
    await api.fail("POST", f"{path}/abort", 422, json={"abort_reason": "dsq", "note": "x" * 501})
    aborted = await api.ok(
        "POST", f"{path}/abort", json={"abort_reason": "dsq", "note": "  Waffe nicht zugelassen "}
    )
    assert (aborted["status"], aborted["abort_reason"]) == ("aborted", "dsq")
    # Dieselbe Ablage wie `POST …/result/abort`: Grund am Ereignis `aborted`.
    (event,) = await api.ok("GET", f"{path}/events")
    assert (event["type"], event["reason"]) == ("aborted", "Waffe nicht zugelassen")
    (details,) = (await _audit(api))["start.aborted"]
    assert details["reason"] == "Waffe nicht zugelassen"
    assert details["start_number"] == entry["start_number"]


async def test_abort_without_note_keeps_working(api: Api, queue_setup: Setup) -> None:
    tid = queue_setup.tid
    entry = await api.entry(tid, queue_setup.class_id)
    (start,) = await api.book(tid, entry["id"], queue_setup.competition_id)
    path = f"/tournaments/{tid}/starts/{start['id']}"
    await api.ok("POST", f"{path}/abort", json={"abort_reason": "dns"})
    (event,) = await api.ok("GET", f"{path}/events")
    assert event["reason"] is None
    assert (await _audit(api))["start.aborted"][0]["reason"] is None


@pytest.fixture
def without_abort_handler(api: Api) -> Iterator[None]:
    handler = hooks.abort_handler()
    if handler is not None:
        hooks.unregister_abort_handler(handler)
    yield
    if handler is not None:
        hooks.register_abort_handler(handler)


async def test_abort_note_without_result_module_goes_to_audit(
    api: Api, queue_setup: Setup, without_abort_handler: None
) -> None:
    tid = queue_setup.tid
    entry = await api.entry(tid, queue_setup.class_id)
    (start,) = await api.book(tid, entry["id"], queue_setup.competition_id)
    await api.ok(
        "POST",
        f"/tournaments/{tid}/starts/{start['id']}/abort",
        json={"abort_reason": "dns", "note": "Nicht erschienen"},
    )
    (details,) = (await _audit(api))["start.aborted"]
    assert (details["reason"], details["abort_reason"]) == ("Nicht erschienen", "dns")
