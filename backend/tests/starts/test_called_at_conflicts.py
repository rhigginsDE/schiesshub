"""Zeitpunkt des Aufrufs (`called_at`) und 409-Antworten mit Feldbezug."""

from datetime import UTC, datetime, timedelta

from tests.starts.conftest import Api, Setup


async def test_called_at_is_set_on_call_and_cleared_on_return(api: Api, queue_setup: Setup) -> None:
    tid, range_id = queue_setup.tid, queue_setup.range_id
    entry = await api.entry(tid, queue_setup.class_id)
    booked = (await api.book(tid, entry["id"], queue_setup.competition_id))[0]
    assert booked["called_at"] is None

    called = await api.ok("POST", f"/tournaments/{tid}/starts/{booked['id']}/call", json={})
    called_at = datetime.fromisoformat(called["called_at"])
    assert abs(datetime.now(UTC) - called_at) < timedelta(minutes=1)

    queue = await api.ok("GET", f"/tournaments/{tid}/ranges/{range_id}/queue")
    lane = next(lane for lane in queue["lanes"] if lane["start"] is not None)
    assert lane["start"]["called_at"] == called["called_at"]
    now = await api.ok("GET", f"/tournaments/{tid}/ranges/{range_id}/now")
    on_lane = next(lane for lane in now["lanes"] if lane["start"] is not None)
    assert on_lane["start"]["called_at"] == called["called_at"]

    returned = await api.ok("POST", f"/tournaments/{tid}/starts/{booked['id']}/return", json={})
    assert returned["called_at"] is None
    queue = await api.ok("GET", f"/tournaments/{tid}/ranges/{range_id}/queue")
    assert queue["waiting"][0]["called_at"] is None

    # Nach dem Abbruch bleibt der Zeitpunkt als Angabe stehen.
    await api.ok("POST", f"/tournaments/{tid}/starts/{booked['id']}/call", json={})
    aborted = await api.ok(
        "POST", f"/tournaments/{tid}/starts/{booked['id']}/abort", json={"abort_reason": "dnf"}
    )
    assert aborted["called_at"] is not None


async def test_field_conflicts_name_the_field(api: Api, queue_setup: Setup) -> None:
    tid = queue_setup.tid
    first = await api.entry(tid, queue_setup.class_id)
    response = await api.client.post(
        f"/api/v1/tournaments/{tid}/entries",
        json={
            "person_id": await api.person(),
            "class_id": queue_setup.class_id,
            "start_number": first["start_number"],
        },
    )
    assert response.status_code == 409
    message = f"Die Startnummer {first['start_number']} ist in diesem Turnier schon vergeben."
    assert response.json() == {
        "detail": message,
        "errors": [{"field": "start_number", "message": message}],
    }

    again = await api.client.post(
        f"/api/v1/tournaments/{tid}/entries",
        json={"person_id": first["person"]["id"], "class_id": queue_setup.class_id},
    )
    assert again.status_code == 409
    assert again.json()["errors"][0]["field"] == "person_id"

    await api.book(tid, first["id"], queue_setup.competition_id)
    limit = await api.client.post(
        f"/api/v1/tournaments/{tid}/entries/{first['id']}/starts",
        json={"competition_id": queue_setup.competition_id},
    )
    assert limit.status_code == 409
    assert limit.json()["errors"] == [{"field": "count", "message": limit.json()["detail"]}]

    # Ohne Feldbezug bleibt es bei `detail`.
    start = (await api.ok("GET", f"/tournaments/{tid}/entries/{first['id']}"))["starts"][0]
    await api.ok("POST", f"/tournaments/{tid}/starts/{start['id']}/call", json={})
    plain = await api.client.post(f"/api/v1/tournaments/{tid}/starts/{start['id']}/call", json={})
    assert plain.status_code == 409
    assert plain.json() == {"detail": "Nur ein wartender Start lässt sich aufrufen."}
