"""Befunde aus dem Audit (22.11.2026): Feed mit älteren Einstellungen, Abgebrochene auf dem
Bildschirm, Kennziffer, Abbruchgrund, Reihenfolge der Startliste."""

import json
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.anzeige.conftest import Api, Setup, shots


def rows(scene: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for group in scene["ranking"]["groups"] for row in group["rows"]]


async def give_up(api: Api, tid: str, sid: str, raw: dict[str, Any] | None) -> None:
    await api.call(tid, sid)
    if raw is not None:
        await api.ok(
            "PUT", f"/tournaments/{tid}/starts/{sid}/raw", json={"raw": raw, "base_seq": 0}
        )
    await api.ok(
        "POST", f"/tournaments/{tid}/starts/{sid}/result/abort", json={"abort_reason": "dnf"}
    )


async def person(api: Api, setup: Setup, cid: str | None = None) -> str:
    entry = await api.entry(setup.tid, setup.class_id)
    return await api.start(setup.tid, entry, cid or setup.cid)


@pytest.mark.parametrize(
    "settings",
    [{}, {"protest_minutes": 30}, {"timezone": None}, {"timezone": "Mars/Olympus"}],
)
async def test_feed_with_old_settings(
    api: Api, setup: Setup, engine: AsyncEngine, settings: dict[str, Any]
) -> None:
    sid = await person(api, setup)
    await api.shoot(setup.tid, sid, shots([9] * 5, [9] * 5))
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE tournament SET settings = CAST(:settings AS jsonb) WHERE id = :id"),
            {"settings": json.dumps(settings), "id": setup.tid},
        )
    display = await api.show(
        {"id": "live", "kind": "live_ranking"},
        {"id": "sieger", "kind": "winners"},
        {"id": "start", "kind": "startlist", "include_finished": True},
        {"id": "stand", "kind": "range", "range_id": setup.range_id},
        tid=setup.tid,
    )
    feed = await api.feed(display)
    assert feed["header"]["timezone"] == "Europe/Berlin"
    assert [scene["kind"] for scene in feed["scenes"]] == ["live_ranking", "winners", "startlist"]


async def test_aborted_hidden_on_screen_unless_wanted(api: Api, setup: Setup) -> None:
    done = await person(api, setup)
    gave_up = await person(api, setup)
    nothing = await person(api, setup)
    await api.shoot(setup.tid, done, shots([9] * 5, [9] * 5))
    await give_up(api, setup.tid, gave_up, shots([10] * 5))
    await give_up(api, setup.tid, nothing, None)

    default = await api.show(
        {"id": "live", "kind": "live_ranking"}, {"id": "sieger", "kind": "winners"}, tid=setup.tid
    )
    live, winners = (await api.feed(default))["scenes"]
    assert [(r["start_id"], r["place"]) for r in rows(live)] == [(done, 1)]
    assert [(r["start_id"], r["place"]) for r in rows(winners)] == [(done, 1)]

    listed = await api.show(
        {"id": "live", "kind": "live_ranking", "show_aborted": True},
        {"id": "sieger", "kind": "winners", "show_aborted": True},
        tid=setup.tid,
    )
    live, winners = (await api.feed(listed))["scenes"]
    for scene in (live, winners):
        # Abgebrochene stehen nie unter den Plätzen, sondern in `unplaced`.
        assert [(r["start_id"], r["place"]) for r in rows(scene)] == [(done, 1)]
        unplaced = [row for group in scene["ranking"]["groups"] for row in group["unplaced"]]
        assert [(r["start_id"], r["place"], r["abort_reason"]) for r in unplaced] == [
            (gave_up, None, "dnf"),
            (nothing, None, "dnf"),
        ]


async def test_competition_code_and_abort_reason(api: Api, setup: Setup) -> None:
    fall = await api.competition(
        setup.tid,
        setup.range_id,
        catalog_federation="bds",
        catalog_code="4401",
        capture_mode="series",
    )
    no_show = await person(api, setup, fall["id"])
    waiting = await person(api, setup, fall["id"])
    await api.ok(
        "POST", f"/tournaments/{setup.tid}/starts/{no_show}/abort", json={"abort_reason": "dns"}
    )
    own = await person(api, setup)
    await api.shoot(setup.tid, own, shots([9] * 5, [9] * 5))

    display = await api.show(
        {"id": "live", "kind": "live_ranking", "show_aborted": True},
        {"id": "start", "kind": "startlist", "include_finished": True},
        tid=setup.tid,
    )
    scenes = (await api.feed(display))["scenes"]
    codes = {(s.get("ranking") or s.get("startlist"))["competition_code"] for s in scenes}
    assert codes == {None, "4401"}
    lists = [s["startlist"] for s in scenes if s["kind"] == "startlist"]
    fall_list = next(item for item in lists if item["competition_code"] == "4401")
    people = {p["start_id"]: p for p in fall_list["starts"]}
    assert people[no_show]["abort_reason"] == "dns"
    assert people[no_show]["competition_code"] == "4401"
    assert people[waiting]["abort_reason"] is None


async def test_startlist_first_attempt_before_second(api: Api, setup: Setup) -> None:
    multi = await api.competition(
        setup.tid,
        setup.range_id,
        name="Mehrfach",
        multi_start=True,
        max_starts=2,
        multi_start_rule="best",
    )
    entry = await api.entry(setup.tid, setup.class_id)
    booked = await api.ok(
        "POST",
        f"/tournaments/{setup.tid}/entries/{entry}/starts",
        201,
        json={"competition_id": multi["id"], "count": 2},
    )
    first, second = (start["id"] for start in booked)
    other_entry = await api.entry(setup.tid, setup.class_id)
    blocker = await api.start(setup.tid, other_entry, multi["id"])
    # Bahn 1 belegt, Versuch 1 auf Bahn 2; danach Versuch 2 auf Bahn 1.
    await api.ok("POST", f"/tournaments/{setup.tid}/starts/{blocker}/call", json={"lane": 1})
    await api.ok("POST", f"/tournaments/{setup.tid}/starts/{first}/call", json={"lane": 2})
    for sid in (blocker, first):
        await api.ok(
            "PUT",
            f"/tournaments/{setup.tid}/starts/{sid}/raw",
            json={"raw": shots([9] * 5, [9] * 5), "base_seq": 0},
        )
        await api.ok(
            "POST", f"/tournaments/{setup.tid}/starts/{sid}/finalize", json={"base_seq": 1}
        )
    await api.shoot(setup.tid, second, shots([8] * 5, [8] * 5))

    display = await api.show(
        {
            "id": "start",
            "kind": "startlist",
            "include_finished": True,
            "competition_ids": [multi["id"]],
        },
        tid=setup.tid,
    )
    (scene,) = (await api.feed(display))["scenes"]
    order = [(p["start_number"], p["attempt"]) for p in scene["startlist"]["starts"]]
    assert order == sorted(order)
    starts = await api.ok("GET", f"/tournaments/{setup.tid}/startlist")
    mine = [(s["start_number"], s["attempt"]) for s in starts if s["competition_id"] == multi["id"]]
    assert mine == sorted(mine)


async def test_ranking_and_startlist_without_catalog_deviations(api: Api, setup: Setup) -> None:
    """Abweichungen vom Katalog zeigt nur die Turnierverwaltung (Entscheidung vom 22.11.2026):
    Die Feed-Szenen haben keine Felder `deviates`/`deviations` mehr."""
    fall = await api.competition(
        setup.tid,
        setup.range_id,
        catalog_federation="bds",
        catalog_code="4401",
        capture_mode="series",
    )
    url = f"/tournaments/{setup.tid}/competitions/{fall['id']}"
    definition = (await api.ok("GET", url))["definition"]
    definition["variant"]["abschnitte"][0]["serien"] = 3
    await api.ok("PATCH", url, json={"definition": definition, "reason": "Ausschreibung"})
    sid = await person(api, setup, fall["id"])
    serie = {"time_cs": 1200, "standing": 0}
    await api.shoot(setup.tid, sid, {"sections": {"fallscheibe": {"series": [serie] * 3}}})
    await person(api, setup, fall["id"])
    own = await person(api, setup)
    await api.shoot(setup.tid, own, shots([9] * 5, [9] * 5))

    display = await api.show(
        {"id": "live", "kind": "live_ranking"},
        {"id": "sieger", "kind": "winners"},
        {"id": "start", "kind": "startlist"},
        tid=setup.tid,
    )
    scenes = (await api.feed(display))["scenes"]
    seen = set()
    for scene in scenes:
        data = scene.get("ranking") or scene.get("startlist")
        seen.add((scene["kind"], data["competition_code"]))
        assert "deviates" not in data, scene["kind"]
        assert "deviations" not in data, scene["kind"]
    assert ("live_ranking", "4401") in seen
    assert ("winners", "4401") in seen
    assert ("startlist", "4401") in seen
    assert ("live_ranking", None) in seen
    # Die Turnierverwaltung kennt die Abweichung weiterhin.
    assert (await api.ok("GET", f"{url}/catalog-diff"))["deviates"] is True
