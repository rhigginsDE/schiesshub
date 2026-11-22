"""Reihenfolge am Stand: Einreihen, Verschieben, Aufrufen, Bahnkollision, Zurückstellen."""

from typing import Any

from tests.starts.conftest import Api, Setup


async def _queue(api: Api, setup: Setup) -> dict[str, Any]:
    return await api.ok("GET", f"/tournaments/{setup.tid}/ranges/{setup.range_id}/queue")


def _waiting(queue: dict[str, Any]) -> list[tuple[int, int]]:
    return [(item["queue_position"], item["start_number"]) for item in queue["waiting"]]


async def _three_waiting(api: Api, setup: Setup) -> list[dict[str, Any]]:
    starts = []
    for _ in range(3):
        entry = await api.entry(setup.tid, setup.class_id)
        starts.extend(await api.book(setup.tid, entry["id"], setup.competition_id))
    return starts


async def test_new_starts_queue_at_the_end_of_their_range(api: Api, queue_setup: Setup) -> None:
    # Zwei Wettbewerbe auf demselben Stand teilen sich die Reihenfolge.
    second = await api.competition(queue_setup.tid, queue_setup.range_id, "Zweiter")
    a = await api.entry(queue_setup.tid, queue_setup.class_id)
    b = await api.entry(queue_setup.tid, queue_setup.class_id)
    await api.book(queue_setup.tid, a["id"], queue_setup.competition_id)
    await api.book(queue_setup.tid, b["id"], second["id"])
    await api.book(queue_setup.tid, b["id"], queue_setup.competition_id)

    queue = await _queue(api, queue_setup)
    assert _waiting(queue) == [(1, 1), (2, 2), (3, 2)]
    assert [item["competition_name"] for item in queue["waiting"]] == [
        "Fallscheibe",
        "Zweiter",
        "Fallscheibe",
    ]
    assert queue["lane_count"] == 2
    assert [lane["lane"] for lane in queue["lanes"]] == [1, 2]


async def test_move_up_down_and_to_position(api: Api, queue_setup: Setup) -> None:
    s1, s2, s3 = await _three_waiting(api, queue_setup)
    path = f"/tournaments/{queue_setup.tid}/starts"

    queue = await api.ok("POST", f"{path}/{s3['id']}/move", json={"direction": "up"})
    assert _waiting(queue) == [(1, 1), (2, 3), (3, 2)]
    queue = await api.ok("POST", f"{path}/{s1['id']}/move", json={"direction": "down"})
    assert _waiting(queue) == [(1, 3), (2, 1), (3, 2)]
    queue = await api.ok("POST", f"{path}/{s2['id']}/move", json={"position": 1})
    assert _waiting(queue) == [(1, 2), (2, 3), (3, 1)]
    # Ganz oben nach oben bleibt oben.
    queue = await api.ok("POST", f"{path}/{s2['id']}/move", json={"direction": "up"})
    assert _waiting(queue) == [(1, 2), (2, 3), (3, 1)]

    detail = await api.fail("POST", f"{path}/{s1['id']}/move", 422, json={"position": 4})
    assert detail == "Die Position muss zwischen 1 und 3 liegen."
    await api.fail("POST", f"{path}/{s1['id']}/move", 422, json={"position": 1, "direction": "up"})
    assert any(event.name == "start.moved" for event in api.drain())


async def test_call_lane_collision_and_gapless_queue(api: Api, queue_setup: Setup) -> None:
    s1, s2, s3 = await _three_waiting(api, queue_setup)
    path = f"/tournaments/{queue_setup.tid}/starts"

    called = await api.ok("POST", f"{path}/{s2['id']}/call", json={"lane": 2})
    assert (called["status"], called["lane"], called["queue_position"]) == ("called", 2, None)
    queue = await _queue(api, queue_setup)
    assert _waiting(queue) == [(1, 1), (2, 3)]
    assert queue["lanes"][1]["start"]["start_id"] == s2["id"]
    assert queue["lanes"][0]["start"] is None

    detail = await api.fail("POST", f"{path}/{s1['id']}/call", 409, json={"lane": 2})
    assert detail == "Bahn 2 ist schon belegt."
    detail = await api.fail("POST", f"{path}/{s1['id']}/call", 422, json={"lane": 3})
    assert detail == "Der Stand hat nur 2 Bahnen."
    # Ohne Bahn: die erste freie.
    assert (await api.ok("POST", f"{path}/{s1['id']}/call", json={}))["lane"] == 1
    detail = await api.fail("POST", f"{path}/{s3['id']}/call", 409, json={})
    assert detail == "Alle Bahnen des Stands sind belegt."


async def test_same_person_not_on_two_lanes(api: Api, queue_setup: Setup) -> None:
    second = await api.competition(queue_setup.tid, queue_setup.range_id, "Zweiter")
    entry = await api.entry(queue_setup.tid, queue_setup.class_id)
    first = (await api.book(queue_setup.tid, entry["id"], queue_setup.competition_id))[0]
    other = (await api.book(queue_setup.tid, entry["id"], second["id"]))[0]
    path = f"/tournaments/{queue_setup.tid}/starts"

    await api.ok("POST", f"{path}/{first['id']}/call", json={})
    detail = await api.fail("POST", f"{path}/{other['id']}/call", 409, json={})
    assert detail.startswith("Startnummer 1 steht gerade schon auf einer Bahn.")


async def test_call_next_fills_free_lanes_and_skips_busy_person(
    api: Api, queue_setup: Setup
) -> None:
    tid = queue_setup.tid
    second = await api.competition(tid, queue_setup.range_id, "Zweiter")
    anna = await api.entry(tid, queue_setup.class_id)
    ben = await api.entry(tid, queue_setup.class_id)
    a1 = (await api.book(tid, anna["id"], queue_setup.competition_id))[0]
    a2 = (await api.book(tid, anna["id"], second["id"]))[0]
    b1 = (await api.book(tid, ben["id"], queue_setup.competition_id))[0]
    call_next = f"/tournaments/{tid}/ranges/{queue_setup.range_id}/call-next"

    called = await api.ok("POST", call_next)
    # Annas zweiter Start wird übersprungen, Ben bekommt Bahn 2.
    assert [(s["id"], s["lane"]) for s in called] == [(a1["id"], 1), (b1["id"], 2)]
    queue = await _queue(api, queue_setup)
    assert [item["start_id"] for item in queue["waiting"]] == [a2["id"]]
    assert queue["waiting"][0]["queue_position"] == 1
    # Alle Bahnen belegt: nichts zu tun.
    assert await api.ok("POST", call_next) == []

    # Ben zurückstellen (hinten): Bahn 2 frei, aber Anna steht noch auf Bahn 1.
    await api.ok("POST", f"/tournaments/{tid}/starts/{b1['id']}/return", json={"position": "back"})
    queue = await _queue(api, queue_setup)
    assert [item["start_id"] for item in queue["waiting"]] == [a2["id"], b1["id"]]
    called = await api.ok("POST", call_next)
    assert [(s["id"], s["lane"]) for s in called] == [(b1["id"], 2)]


async def test_return_to_front_or_back(api: Api, queue_setup: Setup) -> None:
    s1, s2, _ = await _three_waiting(api, queue_setup)
    path = f"/tournaments/{queue_setup.tid}/starts"
    await api.ok("POST", f"{path}/{s1['id']}/call", json={"lane": 1})

    detail = await api.fail("POST", f"{path}/{s2['id']}/return", 409, json={})
    assert detail == "Nur ein aufgerufener Start lässt sich zurückstellen."
    returned = await api.ok("POST", f"{path}/{s1['id']}/return", json={"position": "front"})
    assert (returned["status"], returned["lane"], returned["queue_position"]) == (
        "registered",
        None,
        1,
    )
    assert _waiting(await _queue(api, queue_setup)) == [(1, 1), (2, 2), (3, 3)]

    await api.ok("POST", f"{path}/{s1['id']}/call", json={})
    returned = await api.ok("POST", f"{path}/{s1['id']}/return")
    assert returned["queue_position"] == 3
    assert _waiting(await _queue(api, queue_setup)) == [(1, 2), (2, 3), (3, 1)]


async def test_abort_from_called_frees_lane(api: Api, queue_setup: Setup) -> None:
    s1, s2, _ = await _three_waiting(api, queue_setup)
    path = f"/tournaments/{queue_setup.tid}/starts"
    await api.ok("POST", f"{path}/{s1['id']}/call", json={"lane": 1})
    await api.ok("POST", f"{path}/{s1['id']}/abort", json={"abort_reason": "dnf"})
    called = await api.ok("POST", f"{path}/{s2['id']}/call", json={"lane": 1})
    assert called["lane"] == 1
    assert _waiting(await _queue(api, queue_setup)) == [(1, 3)]
