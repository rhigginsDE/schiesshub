"""Anzeige: Turnier und Szenen in einem Schritt, Feed-Vorschau, genaue Ereignisnamen, Fortschritt
am Stand und Ortszeit."""

from typing import Any

from tests.anzeige.conftest import Api, Setup, precision_definition, shots


async def test_patch_with_config_checks_scenes_against_new_tournament(
    api: Api, setup: Setup
) -> None:
    other = await api.tournament("Anderes Turnier")
    other_range = await api.range(other, name="Stand B")
    display = await api.display("Stand", tournament_id=setup.tid)
    path = f"/displays/{display['id']}"
    scene = {"id": "stand", "kind": "range", "range_id": other_range}

    # Szene passt nur zum neuen Turnier: einzeln gespeichert ginge es in keiner Reihenfolge.
    error = await api.fail("PUT", f"{path}/config", 422, json={"scenes": [scene]})
    assert error["errors"][0]["field"] == "scenes[0].range_id"
    updated = await api.ok(
        "PATCH", path, json={"tournament_id": other, "config": {"scenes": [scene]}}
    )
    assert updated["tournament_id"] == other
    assert [item["id"] for item in updated["config"]["scenes"]] == ["stand"]

    # Zurück zum ersten Turnier mit derselben Szene: Fehler nennt den Pfad in `config`.
    error = await api.fail(
        "PATCH", path, 422, json={"tournament_id": setup.tid, "config": {"scenes": [scene]}}
    )
    assert error["errors"] == [
        {
            "field": "config.scenes[0].range_id",
            "message": "Stand gehört nicht zum Turnier der Anzeige",
        }
    ]
    # Nur `config`: geprüft gegen das gespeicherte Turnier.
    own = {"id": "eigen", "kind": "range", "range_id": setup.range_id}
    error = await api.fail("PATCH", path, 422, json={"config": {"scenes": [own]}})
    assert error["errors"][0]["field"] == "config.scenes[0].range_id"
    await api.fail("PATCH", path, 422, json={"config": None})
    assert (await api.ok("GET", path))["tournament_id"] == other
    api.drain()
    renamed = await api.ok("PATCH", path, json={"name": "Neu", "config": {"scenes": []}})
    assert (renamed["name"], renamed["config"]["scenes"]) == ("Neu", [])
    assert [event.name for event in api.drain()] == ["display.changed"]


async def test_preview_feed_uses_unsaved_config(api: Api, setup: Setup) -> None:
    display = await api.display("Vorschau", tournament_id=setup.tid)
    path = f"/displays/{display['id']}/preview-feed"
    config = {
        "scenes": [{"id": "hinweis", "kind": "notice", "heading": "Siegerehrung"}],
        "theme": "light",
    }
    feed = await api.ok("POST", path, json={"config": config})
    assert [scene["kind"] for scene in feed["scenes"]] == ["notice"]
    assert feed["theme"] == "light"
    assert feed["header"]["tournament_id"] == setup.tid
    # Nichts gespeichert.
    saved = await api.ok("GET", f"/displays/{display['id']}")
    assert [scene["kind"] for scene in saved["config"]["scenes"]] == [
        "live_ranking",
        "startlist",
    ]

    # Ungespeichertes Turnier: null heißt automatisch (hier: kein aktives außer setup).
    other = await api.tournament("Entwurf")
    other_range = await api.range(other)
    scene = {"id": "stand", "kind": "range", "range_id": other_range}
    error = await api.fail("POST", path, 422, json={"config": {"scenes": [scene]}})
    assert error["errors"][0]["field"] == "config.scenes[0].range_id"
    feed = await api.ok("POST", path, json={"config": {"scenes": [scene]}, "tournament_id": other})
    assert feed["header"]["tournament_id"] == other
    assert feed["skipped"][0]["reason"] == "Auf „Stand 1“ ist gerade nichts los."
    feed = await api.ok("POST", path, json={"config": config, "tournament_id": None})
    assert feed["header"]["tournament_mode"] == "auto"


async def test_reload_on_lists_exact_event_names(api: Api, setup: Setup) -> None:
    (display,) = await api.displays()
    feed = await api.feed(display["id"])
    names = feed["reload_on"]
    assert not any(name.endswith("*") for name in names)
    for expected in (
        "display.changed",
        "backup.status",
        "start.status_changed",
        "start.lane_released",
        "result.finalized",
        "result.corrected",
        "tournament.updated",
        "competition.definition_changed",
        "person.updated",
        "club.merged",
        "heat.created",
        "entry.created",
    ):
        assert expected in names
    assert "katalog.importiert" not in names
    assert "auth.login" not in names
    assert names == sorted(names)

    known = await api.ok("GET", "/events/names")
    assert set(names) <= set(known)
    assert "katalog.importiert" in known

    # Ein neu veröffentlichter Name kommt dazu, wenn er zu einem Muster passt.
    api.app.state.events.publish("result.something_new", {})
    assert "result.something_new" in (await api.feed(display["id"]))["reload_on"]
    assert "result.something_new" in await api.ok("GET", "/events/names")


async def _range_page(api: Api, display_id: str) -> dict[str, Any]:
    feed = await api.feed(display_id)
    (page,) = [scene for scene in feed["scenes"] if scene["kind"] == "range"]
    return page["range"]


async def test_range_scene_shows_progress_and_current_series(api: Api) -> None:
    tid = await api.tournament()
    range_id = await api.range(tid, lanes=2)
    class_id = await api.klass(tid)
    cid = (await api.competition(tid, range_id, definition=precision_definition(series=3)))["id"]
    first = await api.start(tid, await api.entry(tid, class_id), cid)
    second = await api.start(tid, await api.entry(tid, class_id), cid)
    await api.call(tid, first)
    await api.call(tid, second)
    display_id = await api.show({"id": "stand", "kind": "range", "range_id": range_id}, tid=tid)

    data = await _range_page(api, display_id)
    (procedure,) = data["procedures"]
    assert procedure["current"] == [
        {"lane": 1, "start_id": first, "section_id": "praezision", "series_number": 1},
        {"lane": 2, "start_id": second, "section_id": "praezision", "series_number": 1},
    ]
    assert [lane["progress"] for lane in data["lanes"]] == [None, None]

    state = await api.ok(
        "PUT",
        f"/tournaments/{tid}/starts/{first}/raw",
        json={"raw": shots([10, 9, 9, 8, 7], [10, 10, 10, 9, 9]), "base_seq": 0},
    )
    data = await _range_page(api, display_id)
    lane_one = data["lanes"][0]
    assert lane_one["start"]["status"] == "captured"
    assert lane_one["progress"] == {
        "section_id": "praezision",
        "series_done": 2,
        "series_total": 3,
        "complete": False,
    }
    assert data["procedures"][0]["current"][0] == {
        "lane": 1,
        "start_id": first,
        "section_id": "praezision",
        "series_number": 3,
    }

    # Vollständig: noch auf der Bahn, aber keine laufende Serie mehr.
    raw = shots([10, 9, 9, 8, 7], [10, 10, 10, 9, 9], [9, 9, 9, 9, 9])
    await api.ok(
        "PUT",
        f"/tournaments/{tid}/starts/{first}/raw",
        json={"raw": raw, "base_seq": state["seq"]},
    )
    data = await _range_page(api, display_id)
    assert data["lanes"][0]["progress"]["complete"] is True
    assert [item["lane"] for item in data["procedures"][0]["current"]] == [2]


async def test_feed_times_in_tournament_timezone(api: Api) -> None:
    tid = await api.tournament(timezone="America/New_York")
    range_id = await api.range(tid, lanes=2)
    class_id = await api.klass(tid)
    cid = (await api.competition(tid, range_id, planning="schedule", heat_minutes=20))["id"]
    heat = await api.ok(
        "POST",
        f"/tournaments/{tid}/ranges/{range_id}/heats",
        201,
        json={"starts_at": "2027-03-06T15:00:00Z", "ends_at": "2027-03-06T15:20:00Z"},
    )
    eid = await api.entry(tid, class_id)
    await api.ok(
        "POST",
        f"/tournaments/{tid}/entries/{eid}/starts",
        201,
        json={"competition_id": cid, "heat_id": heat["id"]},
    )
    display_id = await api.show(
        {"id": "stand", "kind": "range", "range_id": range_id},
        {"id": "liste", "kind": "startlist"},
        tid=tid,
    )
    feed = await api.feed(display_id)
    assert feed["header"]["timezone"] == "America/New_York"
    data = (await _range_page(api, display_id))["next_heat"]
    assert data["starts_at"] == "2027-03-06T15:00:00Z"
    assert data["starts_at_local"] == "2027-03-06T10:00:00-05:00"
    assert data["ends_at_local"] == "2027-03-06T10:20:00-05:00"
    (listing,) = [scene for scene in feed["scenes"] if scene["kind"] == "startlist"]
    (person,) = listing["startlist"]["starts"]
    assert person["heat_starts_at_local"] == "2027-03-06T10:00:00-05:00"

    # Ohne Einstellung (Standard) gilt Europe/Berlin.
    await api.ok("PATCH", f"/tournaments/{tid}", json={"settings": {"timezone": "Europe/Berlin"}})
    feed = await api.feed(display_id)
    assert feed["header"]["timezone"] == "Europe/Berlin"
    (listing,) = [scene for scene in feed["scenes"] if scene["kind"] == "startlist"]
    assert listing["startlist"]["starts"][0]["heat_starts_at_local"] == (
        "2027-03-06T16:00:00+01:00"
    )
