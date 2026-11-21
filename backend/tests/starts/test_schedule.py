"""Zeitplan: Durchgänge, Serie, Kapazität, Überschneidung, nächster freier Platz, Aufruf."""

from typing import Any

import pytest

from tests.starts.conftest import Api, Setup

NINE = "2027-03-06T09:00:00+01:00"


@pytest.fixture
async def plan(api: Api) -> Setup:
    tid = await api.tournament()
    range_id = await api.range(tid, lanes=2)
    class_id = await api.klass(tid)
    competition = await api.competition(
        tid, range_id, "Präzision", planning="schedule", heat_minutes=25
    )
    api.drain()
    return Setup(tid, range_id, class_id, competition["id"])


async def _series(api: Api, plan: Setup, count: int, starts_at: str = NINE) -> list[dict]:
    return await api.ok(
        "POST",
        f"/tournaments/{plan.tid}/ranges/{plan.range_id}/heats/series",
        201,
        json={"competition_id": plan.competition_id, "starts_at": starts_at, "count": count},
    )


async def _next_slot(api: Api, plan: Setup, **params: Any) -> dict | None:
    return await api.ok(
        "GET",
        f"/tournaments/{plan.tid}/competitions/{plan.competition_id}/next-slot",
        params={"after": "2027-03-06T00:00:00Z", **params},
    )


async def test_series_from_competition_minutes(api: Api, plan: Setup) -> None:
    heats = await _series(api, plan, 3)
    assert [(h["number"], h["starts_at"], h["ends_at"]) for h in heats] == [
        (1, "2027-03-06T08:00:00Z", "2027-03-06T08:25:00Z"),
        (2, "2027-03-06T08:25:00Z", "2027-03-06T08:50:00Z"),
        (3, "2027-03-06T08:50:00Z", "2027-03-06T09:15:00Z"),
    ]
    assert all((h["booked"], h["capacity"]) == (0, 2) for h in heats)
    # Weitere Durchgänge schließen mit der Nummer an; überschneiden dürfen sie sich nicht.
    more = await _series(api, plan, 1, "2027-03-06T10:15:00+01:00")
    assert more[0]["number"] == 4
    detail = await api.fail(
        "POST",
        f"/tournaments/{plan.tid}/ranges/{plan.range_id}/heats/series",
        409,
        json={"competition_id": plan.competition_id, "starts_at": NINE, "count": 1},
    )
    assert detail == "Der Durchgang überschneidet sich mit Durchgang 1 auf diesem Stand."
    listed = await api.ok("GET", f"/tournaments/{plan.tid}/ranges/{plan.range_id}/heats")
    assert [h["number"] for h in listed] == [1, 2, 3, 4]


async def test_series_needs_schedule_competition_on_this_range(api: Api, plan: Setup) -> None:
    queue_competition = await api.competition(plan.tid, plan.range_id, "Fallscheibe")
    path = f"/tournaments/{plan.tid}/ranges/{plan.range_id}/heats/series"
    body = {"competition_id": queue_competition["id"], "starts_at": NINE, "count": 2}
    detail = await api.fail("POST", path, 422, json=body)
    assert detail.startswith("Der Wettbewerb wird nicht nach Zeitplan geplant")
    await api.fail("POST", path, 422, json={**body, "starts_at": "2027-03-06T09:00:00"})


async def test_single_heat_create_update_delete(api: Api, plan: Setup) -> None:
    path = f"/tournaments/{plan.tid}/ranges/{plan.range_id}/heats"
    heat = await api.ok(
        "POST",
        path,
        201,
        json={"starts_at": "2027-03-06T13:00:00Z", "ends_at": "2027-03-06T13:30:00Z"},
    )
    assert heat["number"] == 1
    await api.fail(
        "POST",
        path,
        422,
        json={"starts_at": "2027-03-06T13:00:00Z", "ends_at": "2027-03-06T13:00:00Z"},
    )
    changed = await api.ok(
        "PATCH", f"{path}/{heat['id']}", json={"ends_at": "2027-03-06T13:40:00Z"}
    )
    assert changed["ends_at"] == "2027-03-06T13:40:00Z"

    entry = await api.entry(plan.tid, plan.class_id)
    await api.book(plan.tid, entry["id"], plan.competition_id, heat_id=heat["id"])
    detail = await api.fail("DELETE", f"{path}/{heat['id']}", 409)
    assert "noch 1 Start(s) eingeplant" in detail
    events = {event.name for event in api.drain()}
    assert {"heat.created", "heat.updated", "start.booked"} <= events


async def test_capacity_and_lanes(api: Api, plan: Setup) -> None:
    heat = (await _series(api, plan, 1))[0]
    entries = [await api.entry(plan.tid, plan.class_id) for _ in range(3)]
    first = await api.book(plan.tid, entries[0]["id"], plan.competition_id, heat_id=heat["id"])
    assert (first[0]["heat_id"], first[0]["lane"], first[0]["queue_position"]) == (
        heat["id"],
        1,
        None,
    )
    path = f"/tournaments/{plan.tid}/entries/{entries[1]['id']}/starts"
    body = {"competition_id": plan.competition_id, "heat_id": heat["id"]}
    detail = await api.fail("POST", path, 409, json={**body, "lane": 1})
    assert detail == "Bahn 1 im Durchgang 1 ist schon belegt."
    detail = await api.fail("POST", path, 422, json={**body, "lane": 3})
    assert detail == "Der Stand hat nur 2 Bahnen."
    await api.book(plan.tid, entries[1]["id"], plan.competition_id, heat_id=heat["id"], lane=2)

    detail = await api.fail(
        "POST", f"/tournaments/{plan.tid}/entries/{entries[2]['id']}/starts", 409, json=body
    )
    assert detail == "Der Durchgang 1 ist voll (2 Bahnen)."
    heats = await api.ok("GET", f"/tournaments/{plan.tid}/ranges/{plan.range_id}/heats")
    assert heats[0]["booked"] == 2


async def test_person_not_in_overlapping_heats(api: Api, plan: Setup) -> None:
    second_range = await api.range(plan.tid, lanes=4, name="Stand 2")
    other = await api.competition(
        plan.tid, second_range, "Präzision 2", planning="schedule", heat_minutes=40
    )
    heat_a = (await _series(api, plan, 1))[0]
    heat_b = (
        await api.ok(
            "POST",
            f"/tournaments/{plan.tid}/ranges/{second_range}/heats/series",
            201,
            json={
                "competition_id": other["id"],
                "starts_at": "2027-03-06T09:10:00+01:00",
                "count": 1,
            },
        )
    )[0]
    entry = await api.entry(plan.tid, plan.class_id)
    await api.book(plan.tid, entry["id"], plan.competition_id, heat_id=heat_a["id"])
    detail = await api.fail(
        "POST",
        f"/tournaments/{plan.tid}/entries/{entry['id']}/starts",
        409,
        json={"competition_id": other["id"], "heat_id": heat_b["id"]},
    )
    assert detail == "Die Person ist zur selben Zeit schon im Durchgang 1 auf „Stand 1“ eingeplant."

    # Ohne Platz buchen und später einen passenden zuweisen.
    start = (await api.book(plan.tid, entry["id"], other["id"]))[0]
    assert (start["heat_id"], start["queue_position"]) == (None, None)
    later = await api.ok(
        "POST",
        f"/tournaments/{plan.tid}/ranges/{second_range}/heats",
        201,
        json={"starts_at": "2027-03-06T09:00:00Z", "ends_at": "2027-03-06T09:40:00Z"},
    )
    slot_path = f"/tournaments/{plan.tid}/starts/{start['id']}/slot"
    await api.fail("PUT", slot_path, 409, json={"heat_id": heat_b["id"]})
    placed = await api.ok("PUT", slot_path, json={"heat_id": later["id"], "lane": 3})
    assert (placed["heat_id"], placed["lane"]) == (later["id"], 3)
    # Ein Durchgang auf die Zeit eines anderen der Person verschoben: abgelehnt.
    detail = await api.fail(
        "PATCH",
        f"/tournaments/{plan.tid}/ranges/{second_range}/heats/{later['id']}",
        409,
        json={"starts_at": "2027-03-06T07:50:00Z", "ends_at": "2027-03-06T08:05:00Z"},
    )
    assert "zur selben Zeit" in detail
    cleared = await api.ok("DELETE", slot_path)
    assert (cleared["heat_id"], cleared["lane"]) == (None, None)


async def test_next_slot(api: Api, plan: Setup) -> None:
    assert await _next_slot(api, plan) is None
    heat1, heat2, heat3 = await _series(api, plan, 3)
    first = await _next_slot(api, plan)
    assert first is not None
    assert (first["heat"]["id"], first["lane"]) == (heat1["id"], 1)

    entries = [await api.entry(plan.tid, plan.class_id) for _ in range(2)]
    for entry in entries:
        await api.book(plan.tid, entry["id"], plan.competition_id, heat_id=heat1["id"])
    # Durchgang 1 ist voll.
    suggestion = await _next_slot(api, plan)
    assert suggestion is not None
    assert (suggestion["heat"]["id"], suggestion["lane"]) == (heat2["id"], 1)

    # Für eine Person, die in Durchgang 2 schon auf einem anderen Stand eingeplant ist.
    second_range = await api.range(plan.tid, lanes=1, name="Stand 2")
    other = await api.competition(
        plan.tid, second_range, "Andere", planning="schedule", heat_minutes=25
    )
    other_heat = await api.ok(
        "POST",
        f"/tournaments/{plan.tid}/ranges/{second_range}/heats",
        201,
        json={"starts_at": heat2["starts_at"], "ends_at": heat2["ends_at"]},
    )
    busy = await api.entry(plan.tid, plan.class_id)
    await api.book(plan.tid, busy["id"], other["id"], heat_id=other_heat["id"])
    suggestion = await _next_slot(api, plan, entry_id=busy["id"])
    assert suggestion is not None
    assert suggestion["heat"]["id"] == heat3["id"]
    # Ab einer späteren Uhrzeit.
    late = await _next_slot(api, plan, after="2027-03-06T08:30:00Z")
    assert late is not None
    assert late["heat"]["id"] == heat3["id"]

    queue_competition = await api.competition(plan.tid, plan.range_id, "Fallscheibe")
    detail = await api.fail(
        "GET", f"/tournaments/{plan.tid}/competitions/{queue_competition['id']}/next-slot", 409
    )
    assert detail.startswith("Dieser Wettbewerb wird nach Reihenfolge geplant")


async def test_call_heat_shares_lanes_with_queue(api: Api, plan: Setup) -> None:
    heat = (await _series(api, plan, 1))[0]
    a = await api.entry(plan.tid, plan.class_id)
    b = await api.entry(plan.tid, plan.class_id)
    start_a = (await api.book(plan.tid, a["id"], plan.competition_id, heat_id=heat["id"]))[0]
    await api.book(plan.tid, b["id"], plan.competition_id, heat_id=heat["id"])
    # Ein Wettbewerb nach Reihenfolge auf demselben Stand belegt Bahn 2.
    queue_competition = await api.competition(plan.tid, plan.range_id, "Fallscheibe")
    c = await api.entry(plan.tid, plan.class_id)
    start_c = (await api.book(plan.tid, c["id"], queue_competition["id"]))[0]
    await api.ok("POST", f"/tournaments/{plan.tid}/starts/{start_c['id']}/call", json={"lane": 2})

    call_path = f"/tournaments/{plan.tid}/ranges/{plan.range_id}/heats/{heat['id']}/call"
    detail = await api.fail("POST", call_path, 409)
    assert detail.startswith("Bahn 2 ist noch belegt.")
    # Ein einzelner Start des Durchgangs lässt sich auf seine Bahn aufrufen, nicht auf eine andere.
    await api.fail(
        "POST", f"/tournaments/{plan.tid}/starts/{start_a['id']}/call", 422, json={"lane": 2}
    )

    await api.ok(
        "POST",
        f"/tournaments/{plan.tid}/starts/{start_c['id']}/abort",
        json={"abort_reason": "dnf"},
    )
    called = await api.ok("POST", call_path)
    assert [(s["lane"], s["status"]) for s in called] == [(1, "called"), (2, "called")]
    detail = await api.fail("POST", call_path, 409)
    assert detail == "Im Durchgang 1 wartet kein Start."

    # Zurückstellen behält den Platz im Durchgang.
    returned = await api.ok("POST", f"/tournaments/{plan.tid}/starts/{start_a['id']}/return")
    assert (returned["status"], returned["heat_id"], returned["lane"]) == (
        "registered",
        heat["id"],
        1,
    )
