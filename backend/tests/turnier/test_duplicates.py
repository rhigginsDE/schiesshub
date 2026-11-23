"""Doppelte Turniere: gleicher Name (ohne Groß-/Kleinschreibung, Leerzeichen am Rand) und gleiches
Anfangsdatum werden abgelehnt – beim Anlegen, Ändern, Kopieren und aus einer Vorlage."""

from typing import Any

from tests.turnier.conftest import API, Api

MESSAGE = "Ein Turnier mit diesem Namen und Datum gibt es schon."


def _is_duplicate(response: Any) -> None:
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["detail"] == MESSAGE
    assert body["errors"] == [{"field": "name", "message": MESSAGE}]


async def test_create_rejects_same_name_and_date(api: Api) -> None:
    await api.create_tournament(name="Herbstpokal", date_from="2027-10-02")
    api.drain()

    duplicate = await api.client.post(
        f"{API}/tournaments", json={"name": "  herbstPOKAL ", "date_from": "2027-10-02"}
    )

    _is_duplicate(duplicate)
    assert api.drain() == []
    assert len((await api.client.get(f"{API}/tournaments")).json()) == 1


async def test_same_name_on_another_date_is_allowed(api: Api) -> None:
    await api.create_tournament(name="Herbstpokal", date_from="2026-10-03")
    next_year = await api.client.post(
        f"{API}/tournaments", json={"name": "Herbstpokal", "date_from": "2027-10-02"}
    )
    other_name = await api.client.post(
        f"{API}/tournaments", json={"name": "Herbstpokal II", "date_from": "2026-10-03"}
    )

    assert next_year.status_code == 201
    assert other_name.status_code == 201


async def test_update_rejects_collision_but_not_itself(api: Api) -> None:
    first = await api.create_tournament(name="Herbstpokal", date_from="2027-10-02")
    second = await api.create_tournament(name="Frühjahrspokal", date_from="2027-10-02")

    renamed = await api.client.patch(
        f"{API}/tournaments/{second['id']}", json={"name": "HERBSTPOKAL"}
    )
    _is_duplicate(renamed)

    moved = await api.create_tournament(name="Herbstpokal", date_from="2027-10-09")
    redated = await api.client.patch(
        f"{API}/tournaments/{moved['id']}", json={"date_from": "2027-10-02"}
    )
    _is_duplicate(redated)

    # Sich selbst gleich zu benennen (nur andere Schreibweise) ist kein Doppel.
    itself = await api.client.patch(
        f"{API}/tournaments/{first['id']}", json={"name": "Herbstpokal ", "organizer": "SV"}
    )
    assert itself.status_code == 200, itself.text
    unchanged = await api.client.get(f"{API}/tournaments/{second['id']}")
    assert unchanged.json()["name"] == "Frühjahrspokal"


async def test_copy_rejects_collision(api: Api) -> None:
    original = await api.create_tournament(name="Herbstpokal 2026", date_from="2026-10-03")
    await api.create_tournament(name="Herbstpokal 2027", date_from="2027-10-02")

    duplicate = await api.client.post(
        f"{API}/tournaments/{original['id']}/copy",
        json={"name": "herbstpokal 2027", "date_from": "2027-10-02"},
    )
    _is_duplicate(duplicate)
    # Gleicher Name wie das Original ein Jahr später: erlaubt.
    allowed = await api.client.post(
        f"{API}/tournaments/{original['id']}/copy",
        json={"name": "Herbstpokal 2026", "date_from": "2027-10-03"},
    )
    assert allowed.status_code == 201, allowed.text
    assert len((await api.client.get(f"{API}/tournaments")).json()) == 3


async def test_from_template_rejects_collision(api: Api) -> None:
    await api.create_tournament(name="Vereinsmeisterschaft", date_from="2027-05-01")

    duplicate = await api.client.post(
        f"{API}/tournaments/from-template",
        json={
            "template_id": "vereinsmeisterschaft-kurzwaffe",
            "name": "Vereinsmeisterschaft",
            "date_from": "2027-05-01",
        },
    )

    _is_duplicate(duplicate)
    assert len((await api.client.get(f"{API}/tournaments")).json()) == 1
