"""Verwaltung der Anzeigen: Standard-Anzeige, Anlegen, Ändern, Löschen, Prüfung der config."""

from typing import Any

import pytest

from app.modules.anzeige.defaults import DEFAULT_CONFIG
from tests.anzeige.conftest import API, Api, Setup
from tests.conftest import REAL_CATALOG_DIR, ClientFactory


async def test_first_start_creates_main_display_once(start_app: ClientFactory) -> None:
    async with start_app(REAL_CATALOG_DIR) as client:
        (main,) = (await client.get(f"{API}/displays")).json()
        assert main["name"] == "Hauptanzeige"
        assert main["tournament_id"] is None
        assert main["device_id"] is None
        assert [scene["kind"] for scene in main["config"]["scenes"]] == [
            "live_ranking",
            "startlist",
        ]
        assert main["config"] == {
            **DEFAULT_CONFIG,
            "scenes": [
                {
                    **scene,
                    "title": None,
                    **(
                        {
                            "competition_ids": [],
                            "class_ids": [],
                            "rows": 10,
                            "show_running": True,
                            "show_aborted": False,
                        }
                        if scene["kind"] == "live_ranking"
                        else {
                            "competition_ids": [],
                            "range_ids": [],
                            "rows": 12,
                            "include_finished": False,
                        }
                    ),
                }
                for scene in DEFAULT_CONFIG["scenes"]
            ],
        }
        deleted = await client.delete(f"{API}/displays/{main['id']}")
        assert deleted.status_code == 204

    # Neustart: Die gelöschte Hauptanzeige kommt nicht wieder.
    async with start_app(REAL_CATALOG_DIR) as client:
        assert (await client.get(f"{API}/displays")).json() == []
        created = await client.post(f"{API}/displays/defaults")
        assert created.status_code == 201
        assert created.json()["name"] == "Hauptanzeige"
        again = await client.post(f"{API}/displays/defaults")
        assert again.status_code == 409
        assert "schon Anzeigen" in again.json()["detail"]


async def test_crud_and_events(api: Api, setup: Setup) -> None:
    created = await api.display("Aufenthaltsraum")
    display_id = created["id"]
    assert created["config"]["scenes"][0]["kind"] == "live_ranking"
    assert created["sort"] == 1  # nach der Hauptanzeige
    assert [e.data for e in api.drain() if e.name == "display.changed"] == [
        {"display_id": display_id}
    ]

    fetched = await api.ok("GET", f"/displays/{display_id}")
    assert fetched == created

    changed = await api.ok(
        "PATCH",
        f"/displays/{display_id}",
        json={"name": "Fernseher", "tournament_id": setup.tid, "sort": 5},
    )
    assert (changed["name"], changed["tournament_id"], changed["sort"]) == (
        "Fernseher",
        setup.tid,
        5,
    )
    back = await api.ok("PATCH", f"/displays/{display_id}", json={"tournament_id": None})
    assert back["tournament_id"] is None
    assert len([e for e in api.drain() if e.name == "display.changed"]) == 2

    duplicate = await api.fail("POST", "/displays", 409, json={"name": "Hauptanzeige"})
    assert duplicate["detail"] == "Es gibt schon eine Anzeige mit dem Namen „Hauptanzeige“."
    renamed = await api.fail("PATCH", f"/displays/{display_id}", 409, json={"name": "Hauptanzeige"})
    assert "Hauptanzeige" in renamed["detail"]
    null_name = await api.fail("PATCH", f"/displays/{display_id}", 422, json={"name": None})
    assert null_name["errors"][0]["field"] == "name"

    names = [item["name"] for item in await api.displays()]
    assert names == ["Hauptanzeige", "Fernseher"]

    await api.ok("DELETE", f"/displays/{display_id}", 204)
    missing = await api.fail("GET", f"/displays/{display_id}", 404)
    assert missing["detail"] == "Die Anzeige wurde nicht gefunden."
    await api.fail("DELETE", f"/displays/{display_id}", 404)

    audit = await api.ok("GET", "/audit")
    actions = {item["action"] for item in audit["items"]}
    assert {"display.created", "display.updated", "display.deleted"} <= actions


async def test_put_config_and_reorder(api: Api, setup: Setup) -> None:
    display_id = (await api.display())["id"]
    config = {
        "scenes": [
            {"id": "wertung", "kind": "live_ranking", "competition_ids": [setup.cid], "rows": 5},
            {"id": "stand", "kind": "range", "range_id": setup.range_id, "seconds": 30},
            {
                "id": "ehrung",
                "kind": "notice",
                "heading": "Siegerehrung",
                "text": "Um 15:30 Uhr im Saal.",
            },
            {"id": "sieger", "kind": "winners", "top": 3},
        ],
        "name_mode": "short",
        "show_club": False,
        "ticker": "Willkommen beim Vereinspokal",
        "show_backup_warning": True,
        "show_provisional_note": False,
        "theme": "light",
    }
    stored = await api.ok("PUT", f"/displays/{display_id}/config", json=config)
    assert stored["config"]["name_mode"] == "short"
    assert stored["config"]["scenes"][1] == {
        "id": "stand",
        "kind": "range",
        "range_id": setup.range_id,
        "seconds": 30,
        "title": None,
        "next_count": 4,
        "show_procedure": True,
    }

    reordered = await api.ok(
        "POST",
        f"/displays/{display_id}/scenes/reorder",
        json={"ids": ["ehrung", "sieger", "stand", "wertung"]},
    )
    assert [scene["id"] for scene in reordered["config"]["scenes"]] == [
        "ehrung",
        "sieger",
        "stand",
        "wertung",
    ]
    wrong = await api.fail(
        "POST", f"/displays/{display_id}/scenes/reorder", 422, json={"ids": ["ehrung"]}
    )
    assert wrong["errors"][0]["field"] == "ids"
    assert "genau einmal" in wrong["detail"]


def scene(**fields: Any) -> dict[str, Any]:
    return {"id": "a", "kind": "notice", "heading": "Hinweis", **fields}


@pytest.mark.parametrize(
    ("scenes", "field", "message"),
    [
        ([{"id": "a", "kind": "video"}], "scenes[0]", "hat eine unbekannte Art: video"),
        ([scene(farbe="rot")], "scenes[0].notice.farbe", "unbekanntes Feld"),
        ([scene(seconds=4)], "scenes[0].notice.seconds", "muss mindestens 5 sein"),
        ([scene(seconds=601)], "scenes[0].notice.seconds", "darf höchstens 600 sein"),
        ([scene(seconds=10.5)], "scenes[0].notice.seconds", "muss eine ganze Zahl sein"),
        ([scene(id="Groß")], "scenes[0].notice.id", "hat nicht das erwartete Format"),
        ([scene(), scene()], None, "Szenen-ID mehrfach vergeben: a."),
        (
            [{"id": "a", "kind": "live_ranking", "rows": 0}],
            "scenes[0].live_ranking.rows",
            "muss mindestens 1 sein",
        ),
        ([{"id": "a", "kind": "range"}], "scenes[0].range.range_id", "Pflichtfeld fehlt"),
        ([{"id": "a", "kind": "notice"}], "scenes[0].notice.heading", "Pflichtfeld fehlt"),
    ],
)
async def test_config_validation(
    api: Api, scenes: list[dict[str, Any]], field: str | None, message: str
) -> None:
    display_id = (await api.display())["id"]
    body = await api.fail("PUT", f"/displays/{display_id}/config", 422, json={"scenes": scenes})
    assert {"field": field, "message": message} in body["errors"], body


@pytest.mark.parametrize(
    ("config", "field"),
    [
        ({"name_mode": "full"}, "name_mode"),
        ({"theme": "pink"}, "theme"),
        ({"show_club": "yes"}, "show_club"),
        ({"ticker": "x" * 501}, "ticker"),
        ({"blink": True}, "blink"),
    ],
)
async def test_global_options_are_checked(api: Api, config: dict[str, Any], field: str) -> None:
    display_id = (await api.display())["id"]
    body = await api.fail("PUT", f"/displays/{display_id}/config", 422, json=config)
    assert body["errors"][0]["field"] == field


async def test_references_must_exist_and_fit_the_tournament(api: Api, setup: Setup) -> None:
    other = await api.tournament("Anderes Turnier")
    other_range = await api.range(other)
    missing = "00000000-0000-0000-0000-000000000000"
    display_id = (await api.display())["id"]

    body = await api.fail(
        "PUT",
        f"/displays/{display_id}/config",
        422,
        json={
            "scenes": [
                {"id": "a", "kind": "live_ranking", "competition_ids": [setup.cid, missing]},
                {"id": "b", "kind": "range", "range_id": missing},
            ]
        },
    )
    assert body["errors"] == [
        {"field": "scenes[0].competition_ids[1]", "message": "Wettbewerb nicht gefunden"},
        {"field": "scenes[1].range_id", "message": "Stand nicht gefunden"},
    ]

    # Automatisch: Ein Stand eines anderen Turniers ist erlaubt (wird ggf. übersprungen).
    auto = {"scenes": [{"id": "b", "kind": "range", "range_id": other_range}]}
    await api.ok("PUT", f"/displays/{display_id}/config", json=auto)
    # Fest gewählt: Er muss zum Turnier der Anzeige gehören – auch beim Umstellen.
    pinned = await api.fail(
        "PATCH", f"/displays/{display_id}", 422, json={"tournament_id": setup.tid}
    )
    assert pinned["errors"] == [
        {
            "field": "config.scenes[0].range_id",
            "message": "Stand gehört nicht zum Turnier der Anzeige",
        }
    ]
    unknown = await api.fail(
        "PATCH", f"/displays/{display_id}", 422, json={"tournament_id": missing}
    )
    assert unknown["detail"] == "Das Turnier wurde nicht gefunden."
    created = await api.fail(
        "POST",
        "/displays",
        422,
        json={"name": "Neu", "tournament_id": setup.tid, "config": auto},
    )
    assert created["errors"][0]["message"] == "Stand gehört nicht zum Turnier der Anzeige"


async def test_unknown_device_and_display(api: Api) -> None:
    display_id = (await api.display())["id"]
    missing = "00000000-0000-0000-0000-000000000000"
    body = await api.fail("PUT", f"/displays/{display_id}/device", 404, json={"device_id": missing})
    assert body["detail"] == "Das Gerät wurde nicht gefunden."
    await api.fail("GET", f"/displays/{missing}/feed", 404)
    # Ohne Anmeldung (offener Prüfer) gibt es kein Gerät und damit keine eigene Anzeige.
    mine = await api.fail("GET", "/displays/mine", 404)
    assert "keine Anzeige zugewiesen" in mine["detail"]


def test_default_config_is_valid_data() -> None:
    from app.modules.anzeige.schemas import DisplayConfig

    config = DisplayConfig.model_validate(DEFAULT_CONFIG)
    assert [scene.kind for scene in config.scenes] == ["live_ranking", "startlist"]
