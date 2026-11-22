"""Standanzeige und Ranglisten (QA-Durchlauf 2): „Als Nächstes“ je Wettbewerb und Art,
Kennziffer überall, Abgebrochene ohne Scheinwert in eigener Liste."""

from typing import Any

from tests.anzeige.conftest import Api, Setup, shots


async def _person(api: Api, tid: str, class_id: str, name: str, cid: str, **booking: Any) -> str:
    entry = await api.entry(tid, class_id, name)
    booked = await api.ok(
        "POST",
        f"/tournaments/{tid}/entries/{entry}/starts",
        201,
        json={"competition_id": cid, **booking},
    )
    return booked[0]["id"]


async def test_range_upcoming_per_competition_and_kind(api: Api) -> None:
    tid = await api.tournament()
    range_id = await api.range(tid, lanes=3, name="25-m-Stand")
    other_range = await api.range(tid, lanes=2, name="15-m-Stand")
    class_id = await api.klass(tid)
    precision = await api.competition(
        tid,
        range_id,
        catalog_federation="bds",
        catalog_code="1001",
        planning="schedule",
        heat_minutes=30,
    )
    multi = await api.competition(tid, range_id, catalog_federation="bds", catalog_code="1201")
    falling = await api.competition(tid, other_range, catalog_federation="bds", catalog_code="4401")
    await api.status(tid, "active")
    heats = await api.ok(
        "POST",
        f"/tournaments/{tid}/ranges/{range_id}/heats/series",
        201,
        json={
            "competition_id": precision["id"],
            "starts_at": "2027-03-06T09:00:00Z",
            "count": 2,
        },
    )
    karl = await api.entry(tid, class_id, "Karl Weiß")
    karl_multi = (
        await api.ok(
            "POST",
            f"/tournaments/{tid}/entries/{karl}/starts",
            201,
            json={"competition_id": multi["id"]},
        )
    )[0]["id"]
    karl_heat = (
        await api.ok(
            "POST",
            f"/tournaments/{tid}/entries/{karl}/starts",
            201,
            json={"competition_id": precision["id"], "heat_id": heats[1]["id"], "lane": 3},
        )
    )[0]["id"]
    ilse = await api.entry(tid, class_id, "Ilse Bergmann")
    ilse_falling = (
        await api.ok(
            "POST",
            f"/tournaments/{tid}/entries/{ilse}/starts",
            201,
            json={"competition_id": falling["id"]},
        )
    )[0]["id"]
    ilse_multi = (
        await api.ok(
            "POST",
            f"/tournaments/{tid}/entries/{ilse}/starts",
            201,
            json={"competition_id": multi["id"]},
        )
    )[0]["id"]
    jana = await _person(api, tid, class_id, "Jana Hoffmann", multi["id"])
    zofia = await _person(api, tid, class_id, "Zofia Wójcik", multi["id"])
    # Karl schießt 1201 auf Bahn 1, Ilse steht am 15-m-Stand auf Bahn 2.
    await api.ok("POST", f"/tournaments/{tid}/starts/{karl_multi}/call", json={"lane": 1})
    await api.ok("POST", f"/tournaments/{tid}/starts/{ilse_falling}/call", json={"lane": 2})

    display_id = await api.show(
        {"id": "stand", "kind": "range", "range_id": range_id, "next_count": 2}, tid=tid
    )
    (page,) = (await api.feed(display_id))["scenes"]
    data = page["range"]
    schedule, queue = data["upcoming"]

    assert schedule["kind"] == "schedule"
    assert (schedule["competition_code"], schedule["heat_number"]) == ("1001", 2)
    assert schedule["starts_at"] == "2027-03-06T09:30:00Z"
    assert schedule["starts_at_local"] == "2027-03-06T10:30:00+01:00"
    assert schedule["more"] == 0
    (entry,) = schedule["entries"]
    assert entry["start_id"] == karl_heat
    assert (entry["heat_number"], entry["lane"], entry["starts_at_local"]) == (
        2,
        3,
        "2027-03-06T10:30:00+01:00",
    )
    assert (entry["busy"], entry["busy_range_name"], entry["busy_lane"]) == (
        True,
        "25-m-Stand",
        1,
    )
    assert "position" not in entry

    assert queue["kind"] == "queue"
    assert queue["competition_code"] == "1201"
    assert [(e["start_id"], e["position"], e["busy"]) for e in queue["entries"]] == [
        (ilse_multi, 1, True),
        (jana, 2, False),
    ]
    assert queue["more"] == 1
    assert zofia not in str(queue["entries"])
    assert queue["entries"][0]["busy_range_name"] == "15-m-Stand"
    assert all("lane" not in e and "heat_number" not in e for e in queue["entries"])

    # Kennziffer auch am Stand und im Ablauf.
    (lane_one,) = [lane for lane in data["lanes"] if lane["start"]]
    assert lane_one["start"]["competition_code"] == "1201"
    assert {p["competition_code"] for p in data["procedures"]} == {"1201"}

    # Die Sichten des Stands nennen die Kennziffer ebenfalls.
    base = f"/tournaments/{tid}"
    now = await api.ok("GET", f"{base}/ranges/{range_id}/now")
    assert now["lanes"][0]["start"]["competition_code"] == "1201"
    assert {row["competition_code"] for row in now["next_heat_starts"]} == {"1001"}
    queue_view = await api.ok("GET", f"{base}/ranges/{range_id}/queue")
    assert {row["competition_code"] for row in queue_view["waiting"]} == {"1201"}
    startlist = await api.ok("GET", f"{base}/startlist")
    assert {row["competition_code"] for row in startlist} == {"1001", "1201", "4401"}


async def test_range_without_next_count_has_no_upcoming(api: Api, setup: Setup) -> None:
    await api.start(setup.tid, await api.entry(setup.tid, setup.class_id), setup.cid)
    display_id = await api.show(
        {"id": "stand", "kind": "range", "range_id": setup.range_id, "next_count": 0},
        tid=setup.tid,
    )
    (page,) = (await api.feed(display_id))["scenes"]
    assert page["range"]["upcoming"] == []


async def test_aborted_in_own_list_without_fake_value(api: Api, setup: Setup) -> None:
    tid = setup.tid
    done = await api.start(tid, await api.entry(tid, setup.class_id, "Anna Treffer"), setup.cid)
    gave_up = await api.start(tid, await api.entry(tid, setup.class_id, "Karl Weiß"), setup.cid)
    no_show = await api.start(
        tid, await api.entry(tid, setup.class_id, "Rita Fern", display_mode="short"), setup.cid
    )
    disqualified = await api.start(
        tid, await api.entry(tid, setup.class_id, "Dora Voll"), setup.cid
    )
    await api.shoot(tid, done, shots([9] * 5, [9] * 5))
    # Aufgegeben nach einer Serie; disqualifiziert nach vollständiger Erfassung.
    await api.call(tid, gave_up)
    await api.ok(
        "PUT",
        f"/tournaments/{tid}/starts/{gave_up}/raw",
        json={"raw": shots([10] * 5), "base_seq": 0},
    )
    await api.ok(
        "POST", f"/tournaments/{tid}/starts/{gave_up}/result/abort", json={"abort_reason": "dnf"}
    )
    await api.ok("POST", f"/tournaments/{tid}/starts/{no_show}/abort", json={"abort_reason": "dns"})
    await api.call(tid, disqualified)
    await api.ok(
        "PUT",
        f"/tournaments/{tid}/starts/{disqualified}/raw",
        json={"raw": shots([8] * 5, [8] * 5), "base_seq": 0},
    )
    await api.ok(
        "POST",
        f"/tournaments/{tid}/starts/{disqualified}/result/abort",
        json={"abort_reason": "dsq"},
    )

    display_id = await api.show(
        {"id": "live", "kind": "live_ranking", "show_aborted": True},
        {"id": "sieger", "kind": "winners", "show_aborted": True},
        tid=tid,
    )
    live, winners = (await api.feed(display_id))["scenes"]
    for scene in (live, winners):
        (group,) = scene["ranking"]["groups"]
        assert [(row["start_id"], row["place"]) for row in group["rows"]] == [(done, 1)]
        unplaced = {row["start_id"]: row for row in group["unplaced"]}
        assert set(unplaced) == {gave_up, no_show, disqualified}, scene["kind"]
        assert all(row["place"] is None and row["group"] == "unranked" for row in unplaced.values())
        assert unplaced[no_show]["abort_reason"] == "dns"
        assert unplaced[no_show]["score_text"] is None
        assert unplaced[no_show]["series"] == []
        assert unplaced[no_show]["display_name"] == "R. Fern"
        assert unplaced[gave_up]["abort_reason"] == "dnf"
        assert unplaced[gave_up]["score_text"] is None
        assert unplaced[gave_up]["display_name"] == "Karl Weiß"
        assert unplaced[disqualified]["abort_reason"] == "dsq"
        assert unplaced[disqualified]["score_text"] is not None

    # Ohne show_aborted gibt es keine Abgebrochenen, auch nicht unter den Plätzen.
    plain = await api.show({"id": "sieger", "kind": "winners"}, tid=tid)
    (scene,) = (await api.feed(plain))["scenes"]
    (group,) = scene["ranking"]["groups"]
    assert [row["start_id"] for row in group["rows"]] == [done]
    assert group["unplaced"] == []
