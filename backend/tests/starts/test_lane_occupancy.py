"""Bahnbelegung: belegt, solange ein Start aufgerufen oder erfasst ist; frei bei Abschluss,
Abbruch, Zurückstellen oder „Bahn freigeben“. Dazu Fortschritt je Bahn und der 409-Baustein."""

from typing import Any

from tests.starts.conftest import Api, Setup


def _raw(*sums: int) -> dict[str, Any]:
    return {"sections": {"lauf": {"series": [{"sum": value} for value in sums]}}}


async def _queue(api: Api, setup: Setup) -> dict[str, Any]:
    return await api.ok("GET", f"/tournaments/{setup.tid}/ranges/{setup.range_id}/queue")


async def _now(api: Api, setup: Setup) -> dict[str, Any]:
    return await api.ok("GET", f"/tournaments/{setup.tid}/ranges/{setup.range_id}/now")


async def _start(api: Api, setup: Setup) -> dict[str, Any]:
    entry = await api.entry(setup.tid, setup.class_id)
    return (await api.book(setup.tid, entry["id"], setup.competition_id))[0]


async def _put_raw(api: Api, setup: Setup, sid: str, raw: dict[str, Any], seq: int) -> Any:
    path = f"/tournaments/{setup.tid}/starts/{sid}/raw"
    return await api.ok("PUT", path, json={"raw": raw, "base_seq": seq})


def _occupied(view: dict[str, Any]) -> dict[int, tuple[str, str]]:
    return {
        lane["lane"]: (lane["start"]["start_id"], lane["start"]["status"])
        for lane in view["lanes"]
        if lane["start"] is not None
    }


async def test_captured_start_keeps_its_lane(api: Api, queue_setup: Setup) -> None:
    setup = queue_setup
    first, second, third = [await _start(api, setup) for _ in range(3)]
    path = f"/tournaments/{setup.tid}"
    called = (await api.ok("POST", f"{path}/ranges/{setup.range_id}/call-next"))["called"]
    assert [item["id"] for item in called] == [first["id"], second["id"]]
    assert all(item["on_lane"] for item in called)

    state = await _put_raw(api, setup, first["id"], _raw(40), 0)
    assert state["status"] == "captured"
    queue = await _queue(api, setup)
    assert _occupied(queue) == {1: (first["id"], "captured"), 2: (second["id"], "called")}
    assert queue["lanes"][0]["progress"] == {
        "section_id": "lauf",
        "series_done": 1,
        "series_total": 3,
        "complete": False,
        "section_number": 1,
        "section_count": 1,
        "series_done_overall": 1,
        "series_total_overall": 3,
    }
    assert queue["lanes"][1]["progress"] is None
    now = await _now(api, setup)
    assert _occupied(now) == _occupied(queue)
    assert now["lanes"][0]["progress"]["series_done"] == 1
    assert now["lanes"][0]["start"]["on_lane"] is True

    # Keine Bahn frei: „Nächste aufrufen“ ruft niemanden, ein Aufruf auf Bahn 1 scheitert.
    assert (await api.ok("POST", f"{path}/ranges/{setup.range_id}/call-next"))["called"] == []
    response = await api.client.post(f"/api/v1{path}/starts/{third['id']}/call", json={"lane": 1})
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Bahn 1 ist schon belegt.",
        "errors": [{"field": "lane", "message": "Bahn 1 ist schon belegt."}],
    }

    # Abschließen gibt die Bahn frei; die Angabe `lane` bleibt.
    state = await _put_raw(api, setup, first["id"], _raw(40, 41, 42), state["seq"])
    queue = await _queue(api, setup)
    assert queue["lanes"][0]["progress"]["complete"] is True
    await api.ok("POST", f"{path}/starts/{first['id']}/finalize", json={"base_seq": state["seq"]})
    queue = await _queue(api, setup)
    assert _occupied(queue) == {2: (second["id"], "called")}
    rows = await api.ok("GET", f"{path}/startlist")
    row = next(row for row in rows if row["start_id"] == first["id"])
    assert (row["status"], row["lane"], row["on_lane"]) == ("final", 1, False)
    called = (await api.ok("POST", f"{path}/ranges/{setup.range_id}/call-next"))["called"]
    assert [(item["id"], item["lane"]) for item in called] == [(third["id"], 1)]


async def test_release_lane(api: Api, queue_setup: Setup) -> None:
    setup = queue_setup
    start = await _start(api, setup)
    path = f"/tournaments/{setup.tid}/starts/{start['id']}"
    detail = await api.fail("POST", f"{path}/release-lane", 409)
    assert detail == "Der Start steht auf keiner Bahn."
    await api.ok("POST", f"{path}/call", json={})
    detail = await api.fail("POST", f"{path}/release-lane", 409)
    assert "zurückstellen" in detail

    await _put_raw(api, setup, start["id"], _raw(40), 0)
    api.drain()
    released = await api.ok("POST", f"{path}/release-lane")
    assert (released["status"], released["lane"], released["on_lane"]) == ("captured", 1, False)
    events = [event for event in api.drain() if event.name == "start.lane_released"]
    assert [event.data["lane"] for event in events] == [1]
    assert events[0].data["range_id"] == setup.range_id
    assert _occupied(await _queue(api, setup)) == {}
    # Zweimal geht nicht.
    await api.fail("POST", f"{path}/release-lane", 409)

    # Weitere Eingaben bleiben möglich und belegen die Bahn nicht wieder.
    await _put_raw(api, setup, start["id"], _raw(40, 41), 1)
    assert _occupied(await _queue(api, setup)) == {}


async def test_return_and_abort_free_the_lane(api: Api, queue_setup: Setup) -> None:
    setup = queue_setup
    first, second = await _start(api, setup), await _start(api, setup)
    path = f"/tournaments/{setup.tid}/starts"
    await api.ok("POST", f"/tournaments/{setup.tid}/ranges/{setup.range_id}/call-next")
    returned = await api.ok("POST", f"{path}/{first['id']}/return", json={})
    assert (returned["status"], returned["on_lane"]) == ("registered", False)
    await _put_raw(api, setup, second["id"], _raw(40), 0)
    aborted = await api.ok("POST", f"{path}/{second['id']}/abort", json={"abort_reason": "dnf"})
    assert (aborted["status"], aborted["on_lane"]) == ("aborted", False)
    assert _occupied(await _queue(api, setup)) == {}


async def test_capture_without_call_occupies_no_lane(api: Api, queue_setup: Setup) -> None:
    setup = queue_setup
    direct, waiting = await _start(api, setup), await _start(api, setup)
    state = await _put_raw(api, setup, direct["id"], _raw(40), 0)
    assert state["status"] == "captured"
    queue = await _queue(api, setup)
    assert _occupied(queue) == {}
    assert [item["start_id"] for item in queue["waiting"]] == [waiting["id"]]
    path = f"/tournaments/{setup.tid}/ranges/{setup.range_id}/call-next"
    called = (await api.ok("POST", path))["called"]
    assert [(item["id"], item["lane"]) for item in called] == [(waiting["id"], 1)]


async def test_person_on_lane_with_captured_start_is_skipped(api: Api, queue_setup: Setup) -> None:
    """Eine Person steht nur auf einer Bahn – auch, solange ihr erster Start erfasst wird."""
    setup = queue_setup
    second = await api.competition(setup.tid, setup.range_id, "Zweiter")
    entry = await api.entry(setup.tid, setup.class_id)
    first = (await api.book(setup.tid, entry["id"], setup.competition_id))[0]
    later = (await api.book(setup.tid, entry["id"], second["id"]))[0]
    path = f"/tournaments/{setup.tid}"
    await api.ok("POST", f"{path}/starts/{first['id']}/call", json={})
    await _put_raw(api, setup, first["id"], _raw(40), 0)
    result = await api.ok("POST", f"{path}/ranges/{setup.range_id}/call-next")
    assert result["called"] == []
    assert [item["start_id"] for item in result["skipped"]] == [later["id"]]
    detail = await api.fail("POST", f"{path}/starts/{later['id']}/call", 409, json={})
    assert "steht gerade schon auf einer Bahn" in detail


async def test_reopen_does_not_occupy_the_lane_again(api: Api, queue_setup: Setup) -> None:
    setup = queue_setup
    start = await _start(api, setup)
    path = f"/tournaments/{setup.tid}/starts/{start['id']}"
    await api.ok("POST", f"{path}/call", json={})
    state = await _put_raw(api, setup, start["id"], _raw(40, 41, 42), 0)
    state = await api.ok("POST", f"{path}/finalize", json={"base_seq": state["seq"]})
    reopened = await api.ok(
        "POST", f"{path}/reopen", json={"reason": "Tippfehler", "base_seq": state["seq"]}
    )
    assert reopened["status"] == "captured"
    assert _occupied(await _queue(api, setup)) == {}


async def test_field_conflict_keeps_response_shape(api: Api, queue_setup: Setup) -> None:
    """409 mit Feldbezug kommt aus dem gemeinsamen Baustein in `app.core.errors`."""
    entry = await api.entry(queue_setup.tid, queue_setup.class_id)
    response = await api.client.post(
        f"/api/v1/tournaments/{queue_setup.tid}/entries",
        json={
            "person_id": await api.person(),
            "class_id": queue_setup.class_id,
            "start_number": entry["start_number"],
        },
    )
    assert response.status_code == 409
    message = f"Die Startnummer {entry['start_number']} ist in diesem Turnier schon vergeben."
    assert response.json() == {
        "detail": message,
        "errors": [{"field": "start_number", "message": message}],
    }
    # Ohne Feld: nur `detail`.
    start = await _start(api, queue_setup)
    response = await api.client.post(
        f"/api/v1/tournaments/{queue_setup.tid}/starts/{start['id']}/return", json={}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Nur ein aufgerufener Start lässt sich zurückstellen."}
