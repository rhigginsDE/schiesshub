"""Feed der Anzeige mit echten Daten: Szenen, Namensregeln, Ruhe-Szene, Standanzeige, ETag."""

from typing import Any

from app.modules.anzeige import defaults
from tests.anzeige.conftest import API, Api, Setup, shots


def kinds(feed: dict[str, Any]) -> list[str]:
    return [scene["kind"] for scene in feed["scenes"]]


def skipped(feed: dict[str, Any]) -> list[tuple[str, str]]:
    return [(item["scene_id"], item["reason"]) for item in feed["skipped"]]


def rows(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for group in page["ranking"]["groups"] for row in group["rows"]]


async def main_display(api: Api) -> str:
    (display,) = await api.displays()
    return display["id"]


# --- Ruhe-Szene --------------------------------------------------------------


async def test_idle_without_tournament(api: Api) -> None:
    feed = await api.feed(await main_display(api))
    assert feed["header"]["title"] == "Hauptanzeige"
    assert feed["header"]["tournament_id"] is None
    assert feed["header"]["tournament_mode"] == "auto"
    (idle,) = feed["scenes"]
    assert idle["kind"] == "idle"
    assert (idle["heading"], idle["text"]) == ("Hauptanzeige", defaults.IDLE_NO_TOURNAMENT)
    assert skipped(feed) == [
        ("live-wertung", defaults.IDLE_NO_TOURNAMENT),
        ("startliste", defaults.IDLE_NO_TOURNAMENT),
    ]
    assert "result.*" in feed["reload_on"]
    assert "display.changed" in feed["reload_on"]
    assert feed["poll_seconds"] == defaults.POLL_SECONDS


async def test_idle_with_active_tournament_but_nothing_to_show(api: Api, setup: Setup) -> None:
    feed = await api.feed(await main_display(api))
    assert feed["header"]["title"] == "Vereinspokal"
    assert feed["header"]["organizer"] == "SV Muster"
    assert feed["header"]["tournament_status"] == "active"
    (idle,) = feed["scenes"]
    assert (idle["kind"], idle["heading"], idle["text"]) == (
        "idle",
        "Vereinspokal",
        defaults.IDLE_NOTHING_YET,
    )
    assert skipped(feed) == [
        ("live-wertung", "Noch keine Ergebnisse."),
        ("startliste", "Keine offenen Starts."),
    ]


async def test_idle_when_several_tournaments_are_active(api: Api, setup: Setup) -> None:
    other = await api.tournament("Zweites Turnier")
    await api.status(other, "active")
    feed = await api.feed(await main_display(api))
    assert feed["scenes"][0]["text"] == defaults.IDLE_MANY_TOURNAMENTS
    # Fest gewählt geht es trotzdem.
    pinned = await api.show({"id": "info", "kind": "notice", "heading": "Hallo"}, tid=other)
    feed = await api.feed(pinned)
    assert feed["header"]["title"] == "Zweites Turnier"
    assert feed["header"]["tournament_mode"] == "fixed"
    assert kinds(feed) == ["notice"]


async def test_notice_ticker_and_theme_without_tournament(api: Api) -> None:
    display_id = await api.show(
        {
            "id": "ehrung",
            "kind": "notice",
            "heading": "Siegerehrung",
            "text": "Um 15:30 Uhr im Saal.",
            "seconds": 45,
        },
        ticker="Willkommen!",
        theme="light",
    )
    feed = await api.feed(display_id)
    (notice,) = feed["scenes"]
    assert notice == {
        "kind": "notice",
        "scene_id": "ehrung",
        "seconds": 45,
        "title": "Siegerehrung",
        "part": 1,
        "parts": 1,
        "heading": "Siegerehrung",
        "text": "Um 15:30 Uhr im Saal.",
    }
    assert feed["ticker"] == "Willkommen!"
    assert feed["theme"] == "light"
    assert feed["skipped"] == []


# --- Ranglisten, Startliste, Namensregeln --------------------------------------


async def people(api: Api, setup: Setup) -> dict[str, str]:
    """Fünf Starts: drei abgeschlossen, einer läuft, einer wartet."""
    club = await api.club("SV Tell")
    persons = {
        "brandt": {"name": "Markus Brandt", "club_id": club},
        "geheim": {"name": "Geheim Person", "club_id": club, "display_mode": "hidden"},
        "voll": {"name": "Anna Voll", "club_id": club, "display_mode": "short", "show_club": False},
        "laufend": {"name": "Rita Laufend"},
        "wartend": {"name": "Ernst Wartend"},
    }
    starts = {}
    for key, person in persons.items():
        entry = await api.entry(setup.tid, setup.class_id, **person)
        starts[key] = await api.start(setup.tid, entry, setup.cid)
    await api.shoot(setup.tid, starts["brandt"], shots([10] * 5, [9] * 5))
    await api.shoot(setup.tid, starts["geheim"], shots([9] * 5, [9] * 5))
    await api.shoot(setup.tid, starts["voll"], shots([8] * 5, [8] * 5))
    await api.shoot(setup.tid, starts["laufend"], shots([7] * 5), final=False)
    return starts


async def test_live_ranking_and_startlist_respect_name_rules(api: Api, setup: Setup) -> None:
    starts = await people(api, setup)
    feed = await api.feed(await main_display(api))
    assert kinds(feed) == ["live_ranking", "startlist"]
    live, startlist = feed["scenes"]
    assert (live["title"], live["seconds"], live["part"], live["parts"]) == (
        "Live-Wertung",
        20,
        1,
        1,
    )
    assert live["ranking"]["competition_name"] == "Präzision"
    shown = {
        row["start_id"]: (row["place"], row["display_name"], row["club"], row["running"])
        for row in rows(live)
    }
    assert shown == {
        starts["brandt"]: (1, "Markus Brandt", "SV Tell", False),
        starts["geheim"]: (2, None, None, False),
        starts["voll"]: (3, "A. Voll", None, False),
        starts["laufend"]: (4, "Rita Laufend", None, True),
    }
    hidden = next(row for row in rows(live) if row["start_id"] == starts["geheim"])
    assert hidden["start_number"] == 2
    assert [s["start_id"] for s in startlist["startlist"]["starts"]] == [starts["wartend"]]
    assert startlist["startlist"]["more"] == 0
    # Der volle Name einer Person, die ihn nicht freigibt, steht nirgends im Feed.
    text = str(feed)
    assert "Geheim" not in text
    assert "Anna" not in text

    strict = await api.show(
        {"id": "live", "kind": "live_ranking", "show_running": False},
        {"id": "starts", "kind": "startlist", "include_finished": True, "rows": 2},
        name_mode="short",
        show_club=False,
    )
    feed = await api.feed(strict)
    live, startlist = feed["scenes"]
    assert [(row["display_name"], row["club"]) for row in rows(live)] == [
        ("M. Brandt", None),
        (None, None),
        ("A. Voll", None),
    ]
    assert len(startlist["startlist"]["starts"]) == 2
    assert startlist["startlist"]["more"] == 3
    assert "Markus" not in str(feed)

    # show_club=true lockert nicht: Wer seinen Verein nicht zeigt, bleibt ohne.
    loose = await api.show({"id": "live", "kind": "live_ranking"}, show_club=True)
    feed = await api.feed(loose)
    clubs = {row["start_id"]: row["club"] for row in rows(feed["scenes"][0])}
    assert clubs[starts["brandt"]] == "SV Tell"
    assert clubs[starts["voll"]] is None


async def test_winners_rows_and_class_filter(api: Api, setup: Setup) -> None:
    starts = await people(api, setup)
    damen = await api.klass(setup.tid, "damen")
    entry = await api.entry(setup.tid, damen, "Dora Damen")
    dora = await api.start(setup.tid, entry, setup.cid)
    await api.shoot(setup.tid, dora, shots([6] * 5, [6] * 5))

    display_id = await api.show(
        {"id": "sieger", "kind": "winners", "top": 2},
        {"id": "damen", "kind": "live_ranking", "class_ids": [damen]},
        {"id": "kurz", "kind": "live_ranking", "rows": 1, "competition_ids": [setup.cid]},
    )
    feed = await api.feed(display_id)
    winners, ladies, short = feed["scenes"]
    assert winners["title"] == "Siegerliste"
    groups = winners["ranking"]["groups"]
    assert [(g["class_short"], [r["start_id"] for r in g["rows"]]) for g in groups] == [
        ("OFF", [starts["brandt"], starts["geheim"]]),
        ("DAM", [dora]),
    ]
    assert all(row["status"] == "final" for row in rows(winners))
    assert [g["class_short"] for g in ladies["ranking"]["groups"]] == ["DAM"]
    first = short["ranking"]["groups"][0]
    assert [r["start_id"] for r in first["rows"]] == [starts["brandt"]]
    assert first["more"] == 3


async def test_one_page_per_competition_and_skipped_competitions(api: Api, setup: Setup) -> None:
    await people(api, setup)
    second = (await api.competition(setup.tid, setup.range_id, name="Zweite Präzision"))["id"]
    empty = (await api.competition(setup.tid, setup.range_id, name="Ohne Ergebnis"))["id"]
    entry = await api.entry(setup.tid, setup.class_id, "Zora Zweite")
    await api.shoot(setup.tid, await api.start(setup.tid, entry, second), shots([5] * 5, [5] * 5))

    feed = await api.feed(await main_display(api))
    live = [scene for scene in feed["scenes"] if scene["kind"] == "live_ranking"]
    assert [(p["ranking"]["competition_name"], p["part"], p["parts"]) for p in live] == [
        ("Präzision", 1, 2),
        ("Zweite Präzision", 2, 2),
    ]

    chosen = await api.show(
        {"id": "nur", "kind": "live_ranking", "competition_ids": [empty, setup.cid]}
    )
    feed = await api.feed(chosen)
    assert [p["ranking"]["competition_id"] for p in feed["scenes"]] == [setup.cid]
    assert feed["skipped"] == [
        {
            "scene_id": "nur",
            "kind": "live_ranking",
            "reason": "Noch keine Ergebnisse in „Ohne Ergebnis“.",
            "competition_id": empty,
        }
    ]


async def test_provisional_note(api: Api) -> None:
    tid = await api.tournament(protest_minutes=30)
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    cid = (await api.competition(tid, range_id))["id"]
    await api.status(tid, "active")
    sid = await api.start(tid, await api.entry(tid, class_id), cid)
    await api.shoot(tid, sid, shots([10] * 5, [10] * 5))

    feed = await api.feed(await main_display(api))
    (row,) = rows(feed["scenes"][0])
    assert (row["status"], row["provisional"]) == ("provisional", True)
    assert {"code": "provisional", "message": defaults.PROVISIONAL_NOTE} in feed["warnings"]

    quiet = await api.show({"id": "live", "kind": "live_ranking"}, show_provisional_note=False)
    assert (await api.feed(quiet))["warnings"] == []


async def test_backup_warning_only_where_wanted(api: Api) -> None:
    status = await api.ok("GET", "/backup/status")
    warning = status["warning"]
    on = await api.show({"id": "i", "kind": "notice", "heading": "x"}, show_backup_warning=True)
    off = await api.show({"id": "i", "kind": "notice", "heading": "x"}, show_backup_warning=False)
    # Standard (null) folgt der Einstellung der Sicherung: warn_on_display ist aus.
    default = await api.show({"id": "i", "kind": "notice", "heading": "x"})
    codes_on = [w["code"] for w in (await api.feed(on))["warnings"]]
    assert codes_on == ([f"backup_{warning['code']}"] if warning else [])
    assert (await api.feed(off))["warnings"] == []
    assert (await api.feed(default))["warnings"] == []


# --- Standanzeige --------------------------------------------------------------


async def test_range_scene_with_multi_distance_positions(api: Api) -> None:
    tid = await api.tournament()
    range_id = await api.range(tid, lanes=2, name="Stand 3")
    class_id = await api.klass(tid)
    competition = await api.competition(
        tid, range_id, catalog_federation="bds", catalog_code="1201"
    )
    first, second, third = [
        await api.start(tid, await api.entry(tid, class_id, name), competition["id"])
        for name in ("Paul Erster", "Petra Zweite", "Peter Dritter")
    ]
    await api.call(tid, first)
    display_id = await api.show(
        {"id": "stand", "kind": "range", "range_id": range_id, "next_count": 1}, tid=tid
    )
    feed = await api.feed(display_id)
    (page,) = feed["scenes"]
    assert (page["kind"], page["title"]) == ("range", "Stand 3")
    data = page["range"]
    assert [
        (lane["lane"], lane["start"] and lane["start"]["start_id"]) for lane in data["lanes"]
    ] == [
        (1, first),
        (2, None),
    ]
    assert [start["start_id"] for start in data["next"]] == [second]
    assert third not in str(data["next"])

    (procedure,) = data["procedures"]
    assert procedure["catalog_code"] == "1201"
    assert procedure["deviates"] is False
    assert procedure["deviations"] == []
    assert "−1 Ring je volle Sekunde über der Sollzeit" in procedure["notes"]
    fertigkeit, parcours = procedure["sections"]
    assert [s["hit_review_after"] for s in fertigkeit["series"]] == [False, True, False, True]
    assert [s["position"]["nr"] for s in fertigkeit["series"]] == [1, 2, 3, 4]
    assert fertigkeit["series"][0]["position"]["text"] == "stehend, nur schwache Hand"
    assert fertigkeit["series"][0]["time_s"] == 10
    assert parcours["time_measured"] is True
    assert parcours["target_time_s"] == 80
    assert "Sollzeit 80 s" in parcours["summary"]
    assert "auf Zeit" in parcours["summary"]
    six = parcours["series"][1]
    assert six["position"] == {
        "nr": 6,
        "distance_m": 15,
        "stances": [
            {"haltung": "kniend", "hand": "beidhaendig", "text": "kniend, beidhändig"},
            {
                "haltung": "stehend",
                "hand": "schwache_hand",
                "text": "stehend, nur schwache Hand",
            },
        ],
        "target": 2,
        "text": "kniend, beidhändig oder stehend, nur schwache Hand",
    }
    assert six["distance_m"] == 15
    assert all(step["counted"] for step in parcours["series"])


async def test_range_scene_marks_reduced_counted_series(api: Api) -> None:
    tid = await api.tournament()
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    competition = await api.competition(
        tid, range_id, catalog_federation="bds", catalog_code="1001"
    )
    definition = competition["definition"]
    definition["variant"]["abschnitte"][0]["serien_gewertet"] = 1
    await api.ok(
        "PATCH",
        f"/tournaments/{tid}/competitions/{competition['id']}",
        json={"definition": definition},
    )
    await api.start(tid, await api.entry(tid, class_id), competition["id"])
    display_id = await api.show({"id": "stand", "kind": "range", "range_id": range_id}, tid=tid)

    data = (await api.feed(display_id))["scenes"][0]["range"]
    (procedure,) = data["procedures"]
    assert procedure["deviates"] is True
    assert procedure["deviations"]
    (section,) = procedure["sections"]
    assert section["counted_series"] == 1
    assert [step["counted"] for step in section["series"]] == [True, False]
    assert section["deviations"]
    assert "gewertet wird die erste Serie" in section["summary"]
    assert all(lane["start"] is None for lane in data["lanes"])
    assert len(data["next"]) == 1

    hidden = await api.show(
        {"id": "stand", "kind": "range", "range_id": range_id, "show_procedure": False}, tid=tid
    )
    assert (await api.feed(hidden))["scenes"][0]["range"]["procedures"] == []


async def test_range_scene_skipped_when_nothing_happens(api: Api, setup: Setup) -> None:
    other = await api.tournament("Anderes Turnier")
    foreign = await api.range(other, name="Fremder Stand")
    display_id = await api.show(
        {"id": "stand", "kind": "range", "range_id": setup.range_id},
        {"id": "fremd", "kind": "range", "range_id": foreign},
    )
    feed = await api.feed(display_id)
    assert kinds(feed) == ["idle"]
    assert skipped(feed) == [
        ("stand", "Auf „Stand 1“ ist gerade nichts los."),
        ("fremd", "Der Stand gehört nicht zum gezeigten Turnier."),
    ]


# --- ETag ----------------------------------------------------------------------


async def test_etag_and_not_modified(api: Api, setup: Setup) -> None:
    display_id = await main_display(api)
    path = f"{API}/displays/{display_id}/feed"
    first = await api.client.get(path)
    version = first.json()["version"]
    assert first.headers["etag"] == f'"{version}"'
    assert first.headers["cache-control"] == "no-cache"

    again = await api.client.get(path)
    assert again.json()["version"] == version  # Serverzeit zählt nicht zum Inhalt

    unchanged = await api.client.get(path, headers={"If-None-Match": f'"{version}"'})
    assert unchanged.status_code == 304
    assert unchanged.content == b""
    assert unchanged.headers["etag"] == f'"{version}"'
    weak = await api.client.get(path, headers={"If-None-Match": f'W/"{version}", "x"'})
    assert weak.status_code == 304

    sid = await api.start(setup.tid, await api.entry(setup.tid, setup.class_id), setup.cid)
    changed = await api.client.get(path, headers={"If-None-Match": f'"{version}"'})
    assert changed.status_code == 200
    assert changed.json()["version"] != version
    await api.shoot(setup.tid, sid, shots([10] * 5, [10] * 5))
    after_result = await api.client.get(path)
    assert after_result.json()["version"] not in {version, changed.json()["version"]}

    # Umstellen der Anzeige meldet display.changed und ändert den Inhalt.
    api.drain()
    await api.ok("PATCH", f"/displays/{display_id}", json={"name": "Saal"})
    assert [e.data for e in api.drain() if e.name == "display.changed"] == [
        {"display_id": display_id}
    ]
    renamed = await api.client.get(path, headers={"If-None-Match": after_result.headers["etag"]})
    assert renamed.status_code == 200
