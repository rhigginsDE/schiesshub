"""Turniere: Anlegen, Vorlagen, Einstellungen, Statuswechsel, Löschen, Übersicht."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi import HTTPException, Request

from app.core.security import Actor, reset_permission_checker, set_permission_checker
from tests.turnier.conftest import API, Api


async def test_create_with_defaults(api: Api) -> None:
    created = await api.create_tournament(name="Frühjahrspokal", organizer="SV Musterstadt")

    assert created["name"] == "Frühjahrspokal"
    assert created["organizer"] == "SV Musterstadt"
    assert created["date_from"] == created["date_to"] == "2027-03-06"
    assert created["status"] == "draft"
    assert created["template"] == "custom"
    assert created["settings"] == {
        "protest_minutes": None,
        "protest_restart_on_correction": True,
        "timezone": "Europe/Berlin",
        "currency": "EUR",
        "default_fee_first_cents": 0,
        "default_fee_repeat_cents": 0,
        "default_multi_start": False,
        "default_max_starts": 1,
        "default_multi_start_rule": "best",
        "default_changeover_minutes": 5,
        "default_capture_mode": "series",
        "first_start_number": 1,
        "heat_reserve_minutes": 10,
        "display": {},
    }
    assert [event.name for event in api.drain()] == ["tournament.created"]

    fetched = await api.client.get(f"{API}/tournaments/{created['id']}")
    listed = await api.client.get(f"{API}/tournaments")
    assert fetched.json() == created
    assert listed.json() == [created]


async def test_template_club_championship_sets_single_start(api: Api) -> None:
    tournament = await api.create_tournament(template="club_championship")

    assert tournament["settings"]["default_multi_start"] is False
    assert tournament["settings"]["default_max_starts"] == 1
    competition = await api.create(
        tournament["id"], "competitions", catalog_federation="bds", catalog_code="1001"
    )
    assert competition["multi_start"] is False
    assert competition["max_starts"] == 1


async def test_template_open_allows_multi_start_and_given_settings_win(api: Api) -> None:
    tournament = await api.create_tournament(
        template="open", settings={"default_max_starts": 2, "default_fee_first_cents": 1200}
    )

    assert tournament["settings"]["default_multi_start"] is True
    assert tournament["settings"]["default_max_starts"] == 2
    assert tournament["settings"]["default_fee_first_cents"] == 1200


async def test_template_defaults_are_editable_settings(api: Api) -> None:
    tournament = await api.create_tournament(template="club_championship")

    response = await api.client.patch(
        f"{API}/tournaments/{tournament['id']}",
        json={"settings": {"default_multi_start": True, "default_max_starts": 3}},
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["default_multi_start"] is True
    assert settings["default_max_starts"] == 3
    competition = await api.create(
        tournament["id"], "competitions", catalog_federation="bds", catalog_code="1001"
    )
    assert (competition["multi_start"], competition["max_starts"]) == (True, 3)


async def test_update_fields_and_partial_settings(api: Api) -> None:
    tournament = await api.create_tournament(settings={"currency": "CHF", "protest_minutes": 30})
    api.drain()

    response = await api.client.patch(
        f"{API}/tournaments/{tournament['id']}",
        json={
            "name": "Herbstpokal",
            "date_to": "2027-03-07",
            "organizer": None,
            "settings": {"protest_minutes": None, "display": {"theme": "dunkel"}},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Herbstpokal"
    assert body["date_to"] == "2027-03-07"
    assert body["organizer"] is None
    assert body["settings"]["currency"] == "CHF"
    assert body["settings"]["protest_minutes"] is None
    assert body["settings"]["display"] == {"theme": "dunkel"}
    assert [(e.name, e.data) for e in api.drain()] == [
        ("tournament.updated", {"tournament_id": tournament["id"]})
    ]


async def test_unknown_settings_key_is_rejected(api: Api) -> None:
    create = await api.client.post(
        f"{API}/tournaments",
        json={"name": "X", "date_from": "2027-01-01", "settings": {"startgeld": 500}},
    )
    tournament = await api.create_tournament()
    update = await api.client.patch(
        f"{API}/tournaments/{tournament['id']}", json={"settings": {"farbe": "rot"}}
    )

    assert create.status_code == 422
    assert update.status_code == 422
    assert create.json() == {
        "detail": "Unbekanntes Feld ‚settings.startgeld‘.",
        "errors": [{"field": "settings.startgeld", "message": "unbekanntes Feld"}],
    }
    assert update.json()["errors"] == [{"field": "settings.farbe", "message": "unbekanntes Feld"}]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"date_to": "2027-03-01"}, "Das Enddatum liegt vor dem Anfangsdatum."),
        ({"name": None}, "Das Feld „name“ darf nicht leer sein."),
        ({"settings": {"currency": None}}, "Das Feld „currency“ darf nicht leer sein."),
        (
            {"settings": {"default_max_starts": 2}},
            "Ohne Mehrfachstart ist genau ein Start möglich; "
            "die Höchstzahl der Starts muss 1 sein.",
        ),
    ],
)
async def test_invalid_updates_give_german_messages(api: Api, body: dict, message: str) -> None:
    tournament = await api.create_tournament()

    response = await api.client.patch(f"{API}/tournaments/{tournament['id']}", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == message


async def test_strict_types(api: Api) -> None:
    response = await api.client.post(
        f"{API}/tournaments",
        json={"name": "X", "date_from": "2027-01-01", "settings": {"protest_minutes": "30"}},
    )

    assert response.status_code == 422


async def test_unknown_tournament_gives_german_404(api: Api) -> None:
    response = await api.client.get(f"{API}/tournaments/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Das Turnier wurde nicht gefunden."}


# --- Status ------------------------------------------------------------------


async def set_status(api: Api, tournament_id: str, new_status: str) -> int:
    response = await api.client.post(
        f"{API}/tournaments/{tournament_id}/status", json={"status": new_status}
    )
    return response.status_code


async def test_status_goes_forward_step_by_step(api: Api) -> None:
    tournament = await api.create_tournament()
    api.drain()

    assert await set_status(api, tournament["id"], "closed") == 409
    assert await set_status(api, tournament["id"], "draft") == 409
    assert await set_status(api, tournament["id"], "active") == 200
    assert await set_status(api, tournament["id"], "closed") == 200
    assert await set_status(api, tournament["id"], "draft") == 409

    events = [(e.name, e.data) for e in api.drain()]
    assert events == [
        ("tournament.status_changed", {"tournament_id": tournament["id"], "from": f, "to": t})
        for f, t in [("draft", "active"), ("active", "closed")]
    ]


async def test_skipping_a_step_explains_why(api: Api) -> None:
    tournament = await api.create_tournament()

    response = await api.client.post(
        f"{API}/tournaments/{tournament['id']}/status", json={"status": "closed"}
    )

    assert response.json()["detail"] == (
        "Der Status wechselt nur schrittweise: Entwurf, aktiv, abgeschlossen. "
        "Von „Entwurf“ geht es nicht direkt zu „abgeschlossen“."
    )


@pytest.fixture
def permissions() -> Iterator[set[str]]:
    """Berechtigungen des Testbenutzers; der Prüfer lehnt alles andere mit 403 ab."""
    granted: set[str] = set()

    async def checker(request: Request, permission: str) -> Actor:
        if permission not in granted:
            raise HTTPException(status_code=403, detail=f"Berechtigung {permission} fehlt.")
        return Actor(permissions=frozenset(granted))

    set_permission_checker(checker)
    yield granted
    reset_permission_checker()


async def test_reopening_needs_its_own_permission(api: Api, permissions: set[str]) -> None:
    permissions.update({"tournament.read", "tournament.edit"})
    tournament = await api.create_tournament()
    assert await set_status(api, tournament["id"], "active") == 200
    assert await set_status(api, tournament["id"], "closed") == 200

    assert await set_status(api, tournament["id"], "active") == 403
    current = await api.client.get(f"{API}/tournaments/{tournament['id']}")
    assert current.json()["status"] == "closed"

    permissions.add("tournament.reopen")
    assert await set_status(api, tournament["id"], "active") == 200
    assert await set_status(api, tournament["id"], "draft") == 200


async def test_reading_and_editing_need_permissions(api: Api, permissions: set[str]) -> None:
    assert (await api.client.get(f"{API}/tournaments")).status_code == 403
    permissions.add("tournament.read")
    assert (await api.client.get(f"{API}/tournaments")).status_code == 200
    create = await api.client.post(
        f"{API}/tournaments", json={"name": "X", "date_from": "2027-01-01"}
    )
    assert create.status_code == 403


async def test_closed_tournament_is_read_only(api: Api) -> None:
    tournament = await api.create_tournament()
    range_ = await api.create(tournament["id"], "ranges", name="Stand 1", lane_count=5)
    await set_status(api, tournament["id"], "active")
    await set_status(api, tournament["id"], "closed")

    tid = tournament["id"]
    responses = [
        await api.client.patch(f"{API}/tournaments/{tid}", json={"name": "Neu"}),
        await api.client.post(
            f"{API}/tournaments/{tid}/ranges", json={"name": "B", "lane_count": 1}
        ),
        await api.client.patch(
            f"{API}/tournaments/{tid}/ranges/{range_['id']}", json={"name": "C"}
        ),
        await api.client.post(
            f"{API}/tournaments/{tid}/classes/import", json={"federation": "bds"}
        ),
    ]

    assert [response.status_code for response in responses] == [409, 409, 409, 409]
    assert responses[0].json()["detail"] == (
        "Das Turnier ist abgeschlossen. Zum Ändern muss es erst wieder geöffnet werden."
    )


# --- Löschen -----------------------------------------------------------------


async def test_delete_only_in_draft(api: Api) -> None:
    tournament = await api.create_tournament()
    await api.create(tournament["id"], "ranges", name="Stand 1", lane_count=5)
    await api.create(
        tournament["id"], "competitions", catalog_federation="bds", catalog_code="1001"
    )
    await set_status(api, tournament["id"], "active")

    refused = await api.client.delete(f"{API}/tournaments/{tournament['id']}")
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Nur ein Turnier im Entwurf lässt sich löschen. Dieses Turnier ist „aktiv“."
    )

    await set_status(api, tournament["id"], "draft")
    api.drain()
    deleted = await api.client.delete(f"{API}/tournaments/{tournament['id']}")
    assert deleted.status_code == 204
    assert [(e.name, e.data) for e in api.drain()] == [
        ("tournament.deleted", {"tournament_id": tournament["id"]})
    ]
    gone = await api.client.get(f"{API}/tournaments/{tournament['id']}/overview")
    assert gone.status_code == 404


# --- Übersicht ---------------------------------------------------------------


async def test_overview_has_everything_in_one_call(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    range_b = await api.create(tid, "ranges", name="Stand B", lane_count=4)
    range_a = await api.create(tid, "ranges", name="Stand A", lane_count=6, sort=0)
    await api.client.post(f"{API}/tournaments/{tid}/classes/import", json={"federation": "bds"})
    competition = await api.create(
        tid, "competitions", catalog_federation="bds", catalog_code="4401", range_id=range_b["id"]
    )

    response = await api.client.get(f"{API}/tournaments/{tid}/overview")

    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in tournament} == tournament
    assert [r["id"] for r in body["ranges"]] == [range_a["id"], range_b["id"]]
    assert len(body["classes"]) > 0
    assert body["competitions"] == [competition]


async def test_timezone_setting_is_validated(api: Api) -> None:
    tournament = await api.create_tournament(settings={"timezone": "America/New_York"})
    assert tournament["settings"]["timezone"] == "America/New_York"
    path = f"{API}/tournaments/{tournament['id']}"

    response = await api.client.patch(path, json={"settings": {"timezone": "Mond/Basis"}})
    assert response.status_code == 422
    (error,) = response.json()["errors"]
    assert error["field"] == "settings.timezone"
    assert "keine bekannte Zeitzone" in error["message"]
    response = await api.client.patch(path, json={"settings": {"timezone": None}})
    assert response.status_code == 422

    response = await api.client.patch(
        path, json={"settings": {"timezone": "UTC", "protest_restart_on_correction": False}}
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert (settings["timezone"], settings["protest_restart_on_correction"]) == ("UTC", False)


async def test_module_registers_its_event_names(api: Api) -> None:
    """`tournament.deleted` (auch beim Entfernen der Übung) steht in `/events/names`, bevor es
    zum ersten Mal gesendet wurde – angemeldet vom Modul selbst."""
    import re
    from pathlib import Path

    from app.core.events import registered_event_names
    from app.modules import turnier

    names = (await api.client.get(f"{API}/events/names")).json()
    assert "tournament.deleted" in names
    assert set(turnier.EVENT_NAMES) <= registered_event_names()
    # Jeder Name, den das Modul veröffentlicht, ist angemeldet.
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in Path(turnier.__file__).parent.glob("*.py")
    )
    own = r"(?:tournament|range|class|competition)\.[a-z_]+"
    published = set(re.findall(rf'publish\(\s*"({own})"', source))
    assert "tournament.deleted" in published
    assert published <= set(turnier.EVENT_NAMES), published - set(turnier.EVENT_NAMES)
