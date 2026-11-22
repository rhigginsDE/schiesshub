"""Dublettenprüfung ohne Fehlerstatus und Suche in den Vereinen."""

import uuid
from typing import Any

import httpx

from tests.teilnehmer.conftest import API


async def post(api: httpx.AsyncClient, path: str, body: dict[str, Any], status: int = 201) -> Any:
    response = await api.post(f"{API}{path}", json=body)
    assert response.status_code == status, response.text
    return response.json()


async def test_person_check_reports_duplicates_without_error(api: httpx.AsyncClient) -> None:
    tell = (await post(api, "/clubs", {"name": "SV Tell"}))["id"]
    other = (await post(api, "/clubs", {"name": "SG Nord"}))["id"]
    existing = await post(api, "/persons", {"name": "Jürgen Köhler", "club_id": tell})

    found = await post(api, "/persons/check", {"name": " juergen  KOEHLER ", "club_id": tell}, 200)
    assert [person["id"] for person in found["duplicates"]] == [existing["id"]]

    elsewhere = await post(api, "/persons/check", {"name": "Jürgen Köhler", "club_id": other}, 200)
    assert elsewhere == {"duplicates": []}
    without_club = await post(api, "/persons/check", {"name": "Jürgen Köhler"}, 200)
    assert without_club == {"duplicates": []}

    unknown = await api.post(
        f"{API}/persons/check", json={"name": "X", "club_id": str(uuid.uuid4())}
    )
    assert unknown.status_code == 422
    strict = await api.post(f"{API}/persons/check", json={"name": "X", "force": True})
    assert strict.status_code == 422

    # Nichts angelegt; das Anlegen meldet die Dublette weiter mit 409.
    listed = await api.get(f"{API}/persons")
    assert listed.headers["X-Total-Count"] == "1"
    conflict = await api.post(f"{API}/persons", json={"name": "Jürgen Köhler", "club_id": tell})
    assert conflict.status_code == 409
    assert [c["id"] for c in conflict.json()["candidates"]] == [existing["id"]]


async def test_club_search_by_name_and_short(api: httpx.AsyncClient) -> None:
    for name, short in (
        ("Schützenverein Tell", "SV Tell"),
        ("Bogenclub Köln", "BCK"),
        ("Altstadt Schützen", None),
    ):
        await post(api, "/clubs", {"name": name, "short": short} if short else {"name": name})

    async def search(q: str) -> list[str]:
        response = await api.get(f"{API}/clubs", params={"q": q})
        assert response.status_code == 200, response.text
        return [club["name"] for club in response.json()]

    # Treffer am Anfang (Name „Schützenverein …“) vor Teiltreffern („Altstadt Schützen“).
    assert await search("schuetzen") == ["Schützenverein Tell", "Altstadt Schützen"]
    assert await search("bck") == ["Bogenclub Köln"]
    assert await search("koln") == ["Bogenclub Köln"]
    assert await search("tell") == ["Schützenverein Tell"]
    assert await search("xyz") == []
    assert len(await search("  ")) == 3
    everything = (await api.get(f"{API}/clubs")).json()
    assert [club["name"] for club in everything] == [
        "Altstadt Schützen",
        "Bogenclub Köln",
        "Schützenverein Tell",
    ]
