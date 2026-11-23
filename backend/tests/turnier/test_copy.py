"""Turnier kopieren („wie letztes Jahr“): was mitkommt, was nicht, Hinweis auf Katalogänderungen."""

import copy
from pathlib import Path
from typing import Any

import httpx

from tests.conftest import ClientFactory, edit_yaml
from tests.turnier.conftest import API, Api


async def _ok(client: httpx.AsyncClient, method: str, path: str, status: int = 200, **kw: Any):
    response = await client.request(method, f"{API}{path}", **kw)
    assert response.status_code == status, response.text
    return response.json() if response.content else None


async def _original(api: Api) -> dict[str, Any]:
    """Turnier mit allem, was kopiert werden soll, plus Anmeldung, Start und Durchgang."""
    client = api.client
    tournament = await api.create_tournament(
        name="Herbstpokal 2026",
        organizer="SV Musterstadt",
        date_from="2026-10-03",
        date_to="2026-10-04",
        template="open",
        settings={"default_fee_first_cents": 1500, "protest_minutes": 20},
    )
    tid = tournament["id"]
    announcement = await _ok(client, "GET", f"/tournaments/{tid}/announcement")
    announcement["title"] = "Ausschreibung Herbstpokal"
    announcement["facts"]["registration_deadline"] = "2026-09-19"
    announcement["facts"]["venue"] = "Schützenhaus"
    announcement["blocks"][0]["body"] = "Herzlich willkommen."
    await _ok(client, "PUT", f"/tournaments/{tid}/announcement", json=announcement)

    flinte = await api.create(tid, "ranges", name="Flintenstand", lane_count=2)
    kurz = await api.create(tid, "ranges", name="Kurzwaffenstand", lane_count=6)
    offen = await api.create(tid, "classes", code="offen", name="Offene Klasse", short="O")
    damen = await api.create(
        tid, "classes", code="damen", name="Damen", short="D", merge_into_id=offen["id"]
    )
    fallscheibe = await api.create(
        tid,
        "competitions",
        catalog_federation="bds",
        catalog_code="4401",
        range_id=flinte["id"],
        multi_start=True,
        max_starts=3,
        fee_first_cents=1200,
        fee_repeat_cents=600,
        class_ids=[damen["id"]],
    )
    # Bewusste Abweichung: nur 3 Serien gewertet.
    definition = copy.deepcopy(fallscheibe["definition"])
    definition["variant"]["abschnitte"][0]["serien_gewertet"] = 3
    fallscheibe = await _ok(
        client,
        "PATCH",
        f"/tournaments/{tid}/competitions/{fallscheibe['id']}",
        json={"definition": definition, "reason": "Vereinsregel"},
    )
    praezision = await api.create(
        tid, "competitions", catalog_federation="bds", catalog_code="1001", range_id=kurz["id"]
    )
    own = await api.create(
        tid,
        "competitions",
        name="Eigener Wettbewerb",
        definition={k: v for k, v in praezision["definition"].items() if k != "source"},
    )

    person = await _ok(client, "POST", "/persons", 201, json={"name": "Erika Beispiel"})
    entry = await _ok(
        client,
        "POST",
        f"/tournaments/{tid}/entries",
        201,
        json={"person_id": person["id"], "class_id": offen["id"]},
    )
    await _ok(
        client,
        "POST",
        f"/tournaments/{tid}/entries/{entry['id']}/starts",
        201,
        json={"competition_id": praezision["id"]},
    )
    await _ok(
        client,
        "POST",
        f"/tournaments/{tid}/ranges/{kurz['id']}/heats",
        201,
        json={"starts_at": "2026-10-03T09:00:00Z", "ends_at": "2026-10-03T09:15:00Z"},
    )
    return await _ok(client, "GET", f"/tournaments/{tid}/overview") | {
        "own_id": own["id"],
        "fallscheibe_id": fallscheibe["id"],
    }


async def test_copy_takes_setup_but_no_participants(data_api: Api) -> None:
    client = data_api.client
    original = await _original(data_api)
    tid = original["id"]
    data_api.drain()

    response = await client.post(
        f"{API}/tournaments/{tid}/copy",
        json={"name": "Herbstpokal 2027", "date_from": "2027-10-02"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    copied = body["tournament"]
    assert copied["id"] != tid
    assert copied["name"] == "Herbstpokal 2027"
    assert copied["organizer"] == "SV Musterstadt"
    # Dauer wie das Original (zwei Tage).
    assert (copied["date_from"], copied["date_to"]) == ("2027-10-02", "2027-10-03")
    assert copied["status"] == "draft"
    assert copied["is_practice"] is False
    assert copied["template"] == "open"
    assert copied["settings"] == original["settings"]
    assert [e.name for e in data_api.drain()] == ["tournament.created"]

    # Stände und Klassen mit neuen IDs, Zusammenlegung auf die neue Klasse umgehängt.
    assert [(r["name"], r["lane_count"]) for r in copied["ranges"]] == [
        (r["name"], r["lane_count"]) for r in original["ranges"]
    ]
    classes = {c["code"]: c for c in copied["classes"]}
    assert set(classes) == {"offen", "damen"}
    assert classes["damen"]["merge_into_id"] == classes["offen"]["id"]
    assert not {c["id"] for c in copied["classes"]} & {c["id"] for c in original["classes"]}

    # Wettbewerbe mit Definition (samt Abweichung), Startgeld, Mehrfachstart, Zuordnung.
    range_by_name = {r["name"]: r["id"] for r in copied["ranges"]}
    old_range_name = {r["id"]: r["name"] for r in original["ranges"]}
    compared = (
        "name",
        "catalog_federation",
        "catalog_code",
        "definition",
        "capture_mode",
        "multi_start",
        "max_starts",
        "multi_start_rule",
        "fee_first_cents",
        "fee_repeat_cents",
        "combined_ranking",
        "planning",
        "heat_minutes",
        "changeover_minutes",
        "sort",
    )
    assert len(copied["competitions"]) == 3
    for old, new in zip(original["competitions"], copied["competitions"], strict=True):
        assert {k: new[k] for k in compared} == {k: old[k] for k in compared}
        assert new["definition_revision"] == 1
        expected_range = range_by_name[old_range_name[old["range_id"]]] if old["range_id"] else None
        assert new["range_id"] == expected_range
    fallscheibe = copied["competitions"][0]
    assert fallscheibe["definition"]["variant"]["abschnitte"][0]["serien_gewertet"] == 3
    assert fallscheibe["class_ids"] == [classes["damen"]["id"]]

    # Neue Fassung 1, ohne die Geschichte des Originals.
    revisions = await _ok(
        client, "GET", f"/tournaments/{copied['id']}/competitions/{fallscheibe['id']}/revisions"
    )
    assert [r["revision"] for r in revisions] == [1]
    assert revisions[0]["reason"] == "Kopiert aus dem Turnier „Herbstpokal 2026“."

    # Keine Anmeldungen, Starts, Durchgänge.
    assert await _ok(client, "GET", f"/tournaments/{copied['id']}/entries") == []
    for item in copied["ranges"]:
        assert (
            await _ok(client, "GET", f"/tournaments/{copied['id']}/ranges/{item['id']}/heats") == []
        )

    # Ausschreibung mit verschobenem Meldeschluss (gleicher Abstand zum Beginn).
    announcement = await _ok(client, "GET", f"/tournaments/{copied['id']}/announcement")
    assert announcement["title"] == "Ausschreibung Herbstpokal"
    assert announcement["facts"]["venue"] == "Schützenhaus"
    assert announcement["facts"]["registration_deadline"] == "2027-09-18"
    assert announcement["blocks"][0]["body"] == "Herzlich willkommen."

    # Das Original bleibt, wie es war.
    assert len(await _ok(client, "GET", f"/tournaments/{tid}/entries")) == 1


async def test_copy_reports_catalog_state_per_competition(data_api: Api) -> None:
    original = await _original(data_api)

    body = (
        await data_api.client.post(
            f"{API}/tournaments/{original['id']}/copy",
            json={"name": "Kopie", "date_from": "2027-01-01"},
        )
    ).json()

    notes = {item["source_id"]: item for item in body["competitions"]}
    assert set(notes) == {c["id"] for c in original["competitions"]}
    fallscheibe = notes[original["fallscheibe_id"]]
    # Katalog unverändert, aber die bewusste Abweichung bleibt sichtbar.
    assert fallscheibe["catalog_changed"] is False
    assert fallscheibe["catalog_stand_then"] == fallscheibe["catalog_stand_now"]
    assert fallscheibe["catalog_diff"]["deviates"] is True
    assert [d["path"] for d in fallscheibe["catalog_diff"]["differences"]] == [
        "variant.abschnitte[0].serien_gewertet"
    ]
    own = notes[original["own_id"]]
    assert own["catalog_changed"] is False
    assert own["catalog_code"] is None
    assert own["catalog_diff"]["deviates"] is False


async def test_copy_after_catalog_change_keeps_the_original_definition(
    start_app: ClientFactory, catalog_copy: Path
) -> None:
    async with start_app(catalog_copy) as client:
        tournament = await _ok(
            client, "POST", "/tournaments", 201, json={"name": "VM 2026", "date_from": "2026-05-01"}
        )
        competition = await _ok(
            client,
            "POST",
            f"/tournaments/{tournament['id']}/competitions",
            201,
            json={"catalog_federation": "bds", "catalog_code": "4401"},
        )

    def more_targets(data: dict) -> None:
        data["ablaeufe"]["fallscheibe-max6"]["varianten"][0]["abschnitte"][0]["serien"] = 5

    edit_yaml(catalog_copy / "bds" / "gruppen" / "flinte-15m-fallscheibe.yaml", more_targets)

    async with start_app(catalog_copy) as client:
        body = await _ok(
            client,
            "POST",
            f"/tournaments/{tournament['id']}/copy",
            201,
            json={"name": "VM 2027", "date_from": "2027-05-01"},
        )

    note = body["competitions"][0]
    assert note["source_id"] == competition["id"]
    assert note["catalog_changed"] is True
    assert note["catalog_diff"]["deviates"] is True
    assert note["catalog_diff"]["differences"][0]["catalog_value"] == 5
    assert note["catalog_diff"]["differences"][0]["tournament_value"] == 4
    # Die Kopie behält die Definition des Originals; übernehmen ist ein eigener Schritt.
    copied = body["tournament"]["competitions"][0]
    assert copied["definition"] == competition["definition"]


async def test_copy_options_and_errors(api: Api) -> None:
    original = await api.create_tournament(organizer="SV Musterstadt", date_to="2027-03-07")
    path = f"{API}/tournaments/{original['id']}/copy"

    explicit = await api.client.post(
        path,
        json={
            "name": "Kopie",
            "date_from": "2028-01-01",
            "date_to": "2028-01-01",
            "organizer": None,
        },
    )
    assert explicit.status_code == 201
    assert explicit.json()["tournament"]["organizer"] is None
    assert explicit.json()["tournament"]["date_to"] == "2028-01-01"
    assert explicit.json()["competitions"] == []

    backwards = await api.client.post(
        path, json={"name": "Kopie", "date_from": "2028-01-02", "date_to": "2028-01-01"}
    )
    assert backwards.status_code == 422
    assert backwards.json()["detail"] == "Das Enddatum liegt vor dem Anfangsdatum."

    missing = await api.client.post(
        f"{API}/tournaments/00000000-0000-0000-0000-000000000000/copy",
        json={"name": "Kopie", "date_from": "2028-01-01"},
    )
    assert missing.status_code == 404

    unknown_field = await api.client.post(
        path, json={"name": "Kopie", "date_from": "2028-01-01", "status": "active"}
    )
    assert unknown_field.status_code == 422
