"""Starts buchen: Mehrfachstart, Beträge, Klassen, Storno, Abbruch, Statusübergänge."""

import uuid

import pytest
from fastapi import HTTPException

from app.core.security import Actor
from app.modules.starts import lifecycle
from tests.starts.conftest import Api, Setup


async def _multi(api: Api, setup: Setup, **fields: object) -> str:
    competition = await api.competition(
        setup.tid,
        setup.range_id,
        "Mehrfach",
        planning="queue",
        multi_start=True,
        max_starts=3,
        fee_first_cents=1500,
        fee_repeat_cents=800,
        **fields,
    )
    return competition["id"]


async def test_single_start_competition_allows_one(api: Api, queue_setup: Setup) -> None:
    entry = await api.entry(queue_setup.tid, queue_setup.class_id)
    path = f"/tournaments/{queue_setup.tid}/entries/{entry['id']}/starts"
    await api.book(queue_setup.tid, entry["id"], queue_setup.competition_id)
    detail = await api.fail("POST", path, 409, json={"competition_id": queue_setup.competition_id})
    assert detail == "In diesem Wettbewerb ist nur ein Start je Person möglich."


async def test_multi_start_fees_and_maximum(api: Api, queue_setup: Setup) -> None:
    cid = await _multi(api, queue_setup)
    entry = await api.entry(queue_setup.tid, queue_setup.class_id)

    starts = await api.book(queue_setup.tid, entry["id"], cid, count=2)
    assert [(s["attempt"], s["fee_cents"], s["status"]) for s in starts] == [
        (1, 1500, "registered"),
        (2, 800, "registered"),
    ]
    detail = await api.fail(
        "POST",
        f"/tournaments/{queue_setup.tid}/entries/{entry['id']}/starts",
        409,
        json={"competition_id": cid, "count": 2},
    )
    assert detail == (
        "In diesem Wettbewerb sind höchstens 3 Starts je Person möglich; gebucht sind schon 2."
    )
    third = await api.book(queue_setup.tid, entry["id"], cid)
    assert (third[0]["attempt"], third[0]["fee_cents"]) == (3, 800)

    detail_entry = await api.ok("GET", f"/tournaments/{queue_setup.tid}/entries/{entry['id']}")
    assert detail_entry["fee_total_cents"] == 1500 + 800 + 800
    assert len(detail_entry["starts"]) == 3


async def test_fee_is_frozen_at_booking(api: Api, queue_setup: Setup) -> None:
    cid = await _multi(api, queue_setup)
    entry = await api.entry(queue_setup.tid, queue_setup.class_id)
    await api.book(queue_setup.tid, entry["id"], cid)
    await api.ok(
        "PATCH",
        f"/tournaments/{queue_setup.tid}/competitions/{cid}",
        json={"fee_first_cents": 2000, "fee_repeat_cents": 1000},
    )
    await api.book(queue_setup.tid, entry["id"], cid)
    other = await api.entry(queue_setup.tid, queue_setup.class_id)
    await api.book(queue_setup.tid, other["id"], cid)

    mine = await api.ok("GET", f"/tournaments/{queue_setup.tid}/entries/{entry['id']}")
    theirs = await api.ok("GET", f"/tournaments/{queue_setup.tid}/entries/{other['id']}")
    assert [s["fee_cents"] for s in mine["starts"]] == [1500, 1000]
    assert [s["fee_cents"] for s in theirs["starts"]] == [2000]


async def test_class_admission(api: Api, queue_setup: Setup) -> None:
    tid = queue_setup.tid
    ladies = await api.klass(tid, "damen", "Damen")
    only_ladies = await api.competition(tid, queue_setup.range_id, "Damenpokal", class_ids=[ladies])
    open_entry = await api.entry(tid, queue_setup.class_id)
    lady = await api.entry(tid, ladies)

    detail = await api.fail(
        "POST",
        f"/tournaments/{tid}/entries/{open_entry['id']}/starts",
        409,
        json={"competition_id": only_ladies["id"]},
    )
    assert detail == "Die Klasse „Offene Klasse“ ist im Wettbewerb „Damenpokal“ nicht zugelassen."
    await api.book(tid, lady["id"], only_ladies["id"])
    # Leere Liste: alle Klassen zugelassen.
    await api.book(tid, open_entry["id"], queue_setup.competition_id)
    await api.book(tid, lady["id"], queue_setup.competition_id)


async def test_competition_of_other_tournament_and_lane_without_heat(
    api: Api, queue_setup: Setup
) -> None:
    other = await api.tournament()
    foreign = await api.competition(other, None)
    entry = await api.entry(queue_setup.tid, queue_setup.class_id)
    path = f"/tournaments/{queue_setup.tid}/entries/{entry['id']}/starts"
    detail = await api.fail("POST", path, 422, json={"competition_id": foreign["id"]})
    assert detail == "Der Wettbewerb gehört nicht zu diesem Turnier."
    detail = await api.fail(
        "POST", path, 422, json={"competition_id": queue_setup.competition_id, "lane": 1}
    )
    assert detail.startswith("Eine Bahn lässt sich beim Buchen nur zusammen mit einem Durchgang")


async def test_cancel_only_registered_and_attempts_close_up(api: Api, queue_setup: Setup) -> None:
    tid = queue_setup.tid
    cid = await _multi(api, queue_setup)
    entry = await api.entry(tid, queue_setup.class_id)
    first, second, third = await api.book(tid, entry["id"], cid, count=3)

    await api.ok("DELETE", f"/tournaments/{tid}/starts/{first['id']}", 204)
    starts = (await api.ok("GET", f"/tournaments/{tid}/entries/{entry['id']}"))["starts"]
    # Die Versuche rücken nach, die Beträge bleiben an ihrer Position.
    assert [(s["id"], s["attempt"], s["fee_cents"]) for s in starts] == [
        (second["id"], 1, 1500),
        (third["id"], 2, 800),
    ]
    events = [event for event in api.drain() if event.name == "start.cancelled"]
    assert [event.data["start_id"] for event in events] == [first["id"]]

    await api.ok("POST", f"/tournaments/{tid}/starts/{second['id']}/call", json={})
    detail = await api.fail("DELETE", f"/tournaments/{tid}/starts/{second['id']}", 409)
    assert "nur noch abbrechen" in detail


async def test_abort_with_reason(api: Api, queue_setup: Setup) -> None:
    tid = queue_setup.tid
    entry = await api.entry(tid, queue_setup.class_id)
    start = (await api.book(tid, entry["id"], queue_setup.competition_id))[0]
    path = f"/tournaments/{tid}/starts/{start['id']}/abort"
    await api.fail("POST", path, 422, json={"abort_reason": "krank"})
    await api.fail("POST", path, 422, json={})

    aborted = await api.ok("POST", path, json={"abort_reason": "dns"})
    assert (aborted["status"], aborted["abort_reason"], aborted["queue_position"]) == (
        "aborted",
        "dns",
        None,
    )
    detail = await api.fail("POST", path, 409, json={"abort_reason": "dsq"})
    assert detail == "Ein Start im Status „abgebrochen“ kann nicht „abgebrochen“ werden."
    status_events = [e for e in api.drain() if e.name == "start.status_changed"]
    assert status_events[-1].data["to"] == "aborted"


async def test_lifecycle_for_result_module(api: Api, queue_setup: Setup) -> None:
    """Die öffentliche Funktion: erfassen, abschließen, wiederöffnen; verbotene Übergänge."""
    tid = queue_setup.tid
    entry = await api.entry(tid, queue_setup.class_id)
    start = (await api.book(tid, entry["id"], queue_setup.competition_id))[0]
    start_id = uuid.UUID(start["id"])
    actor = Actor()
    factory = api.app.state.session_factory

    async with factory() as session:
        loaded = await lifecycle.load_start(session, start_id)
        with pytest.raises(HTTPException) as refused:
            await lifecycle.transition(session, loaded, "final", actor)
    assert refused.value.status_code == 409
    assert refused.value.detail == (
        "Ein Start im Status „angemeldet“ kann nicht „abgeschlossen“ werden."
    )

    called = await api.ok("POST", f"/tournaments/{tid}/starts/{start['id']}/call", json={})
    assert called["lane"] == 1

    async with factory() as session:
        loaded = await lifecycle.load_start(session, start_id)
        change = await lifecycle.transition(session, loaded, "captured", actor)
        await session.commit()
        lifecycle.publish_status(api.app.state.events, change)
    assert (change.previous, change.current) == ("called", "captured")
    # Erfasst: Die Bahn bleibt belegt, der Schütze schießt noch.
    queue = await api.ok("GET", f"/tournaments/{tid}/ranges/{queue_setup.range_id}/queue")
    assert [lane["start"] and lane["start"]["status"] for lane in queue["lanes"]] == [
        "captured",
        None,
    ]

    async with factory() as session:
        loaded = await lifecycle.load_start(session, start_id)
        await lifecycle.transition(session, loaded, "final", actor)
        await session.commit()
    # Abgeschlossen: Die Bahn ist wieder frei, `lane` bleibt als Angabe stehen.
    queue = await api.ok("GET", f"/tournaments/{tid}/ranges/{queue_setup.range_id}/queue")
    assert all(lane["start"] is None for lane in queue["lanes"])
    entry_now = await api.ok("GET", f"/tournaments/{tid}/entries/{entry['id']}")
    assert (entry_now["starts"][0]["lane"], entry_now["starts"][0]["on_lane"]) == (1, False)
    async with factory() as session:
        loaded = await lifecycle.load_start(session, start_id)
        with pytest.raises(HTTPException, match="Grund"):
            await lifecycle.transition(session, loaded, "captured", actor)
    async with factory() as session:
        loaded = await lifecycle.load_start(session, start_id)
        await lifecycle.transition(session, loaded, "captured", actor, reason="Tippfehler")
        await session.commit()

    detail = await api.fail("POST", f"/tournaments/{tid}/starts/{start['id']}/call", 409, json={})
    assert detail == "Nur ein wartender Start lässt sich aufrufen."
    names = [event.name for event in api.drain()]
    assert "start.status_changed" in names


async def test_capture_without_call_leaves_lane_empty(api: Api, queue_setup: Setup) -> None:
    """`registered → captured`: nachträgliche Erfassung ohne Aufrufen (Reihenfolge)."""
    tid = queue_setup.tid
    first = (
        await api.book(
            tid, (await api.entry(tid, queue_setup.class_id))["id"], queue_setup.competition_id
        )
    )[0]
    second = (
        await api.book(
            tid, (await api.entry(tid, queue_setup.class_id))["id"], queue_setup.competition_id
        )
    )[0]
    factory = api.app.state.session_factory
    async with factory() as session:
        loaded = await lifecycle.load_start(session, uuid.UUID(first["id"]))
        change = await lifecycle.transition(session, loaded, "captured", Actor())
        await session.commit()
    assert (change.previous, change.current) == ("registered", "captured")

    entry_starts = await api.ok("GET", f"/tournaments/{tid}/startlist")
    row = next(row for row in entry_starts if row["start_id"] == first["id"])
    assert (row["status"], row["lane"], row["queue_position"]) == ("captured", None, None)
    queue = await api.ok("GET", f"/tournaments/{tid}/ranges/{queue_setup.range_id}/queue")
    assert [(s["start_id"], s["queue_position"]) for s in queue["waiting"]] == [(second["id"], 1)]
    assert all(lane["start"] is None for lane in queue["lanes"])
