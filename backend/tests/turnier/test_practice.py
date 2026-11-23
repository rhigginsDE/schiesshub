"""Übungsturnier: Beispieldaten über die echten Abläufe, nur eines, rückstandslos entfernbar."""

from collections import Counter
from typing import Any

import pytest
import yaml
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.turnier import practice
from app.modules.turnier.practice import PRACTICE_FILE, load_practice
from tests.conftest import REAL_CATALOG_DIR
from tests.turnier.conftest import API, Api


async def _get(api: Api, path: str, **params: Any) -> Any:
    response = await api.client.get(f"{API}{path}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _count(engine: AsyncEngine, sql: str, **params: Any) -> int:
    async with engine.connect() as connection:
        return (await connection.execute(text(sql), params)).scalar_one()


async def _practice(api: Api) -> dict[str, Any]:
    response = await api.client.post(f"{API}/tournaments/practice")
    assert response.status_code == 201, response.text
    return response.json()


def test_practice_file_is_valid_and_fictional() -> None:
    data = load_practice()
    classes = yaml.safe_load((REAL_CATALOG_DIR / "bds" / "klassen.yaml").read_text("utf-8"))
    codes = {item["id"] for item in classes["klassen"]}

    assert 10 <= len(data.persons) <= 14
    assert 2 <= len(data.clubs) <= 3
    assert len(data.ranges) == 2
    assert 2 <= len(data.competitions) <= 3
    assert {person.class_code for person in data.persons} <= codes
    states = Counter(start.state for person in data.persons for start in person.starts)
    assert set(states) == {"registered", "called", "captured", "final", "aborted"}
    # Kein Geburtsdatum, kein Geburtsjahr – in keinem Datenfeld der Datei (Kommentare zählen
    # nicht); unbekannte Felder lehnt das Dateiformat ohnehin ab.
    lines = PRACTICE_FILE.read_text(encoding="utf-8").lower().splitlines()
    content = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
    assert "geburt" not in content
    assert "birth" not in content
    # Als Übung erkennbare Vereine.
    assert any("Übung" in club.name for club in data.clubs)


async def test_practice_tournament_has_sample_data_in_all_states(data_api: Api) -> None:
    created = await _practice(data_api)
    tid = created["id"]

    assert created["is_practice"] is True
    assert created["status"] == "active"
    assert created["date_from"] == created["date_to"]
    assert len(created["ranges"]) == 2
    codes = [c["catalog_code"] for c in created["competitions"]]
    assert codes == ["4401", "4403", "1001"]
    plannings = {c["catalog_code"]: c["planning"] for c in created["competitions"]}
    # Fallscheibe Flinte 15 m nach Reihenfolge, Präzision nach Zeitplan.
    assert plannings == {"4401": "queue", "4403": "queue", "1001": "schedule"}
    listed = await _get(data_api, "/tournaments")
    assert [t["is_practice"] for t in listed] == [True]

    entries = await _get(data_api, f"/tournaments/{tid}/entries")
    assert len(entries) == 12
    statuses = Counter(start["status"] for entry in entries for start in entry["starts"])
    assert set(statuses) == {"registered", "called", "captured", "final", "aborted"}
    aborted = [s for e in entries for s in e["starts"] if s["status"] == "aborted"]
    assert [s["abort_reason"] for s in aborted] == ["dnf"]
    # Mehrfachstart mit Nachkauf.
    repeat = [s for e in entries for s in e["starts"] if s["attempt"] == 2]
    assert len(repeat) == 1
    assert repeat[0]["fee_cents"] == 500

    items = await _get(data_api, "/persons", limit=100)
    assert len(items) == 12
    assert all(p["member_no"].startswith("ÜBUNG-") for p in items)
    assert all("birth" not in key and "geburt" not in key for p in items for key in p)
    clubs = await _get(data_api, "/clubs")
    assert {c["name"] for c in clubs} == {
        "Übungsverein Musterstadt",
        "Probeschützen Beispielhausen",
        "Testgilde Vorlagendorf",
    }

    # Wertung über die echten Services: Fallscheibe aufsteigend nach Zeit plus Zuschlag.
    fallscheibe = created["competitions"][0]
    ranking = await _get(
        data_api, f"/tournaments/{tid}/competitions/{fallscheibe['id']}/ranking", scope="live"
    )
    rows = [row for group in ranking["groups"] for row in group["rows"]]
    ranked = [row for row in rows if row["group"] == "ranked"]
    assert len(ranked) >= 4
    assert any(row["abort_reason"] == "dnf" and row["place"] is None for row in rows)

    # Durchgänge des Zeitplans um die aktuelle Uhrzeit.
    kurzwaffe = next(r for r in created["ranges"] if "Kurzwaffe" in r["name"])
    heats = await _get(data_api, f"/tournaments/{tid}/ranges/{kurzwaffe['id']}/heats")
    assert [h["number"] for h in heats] == [1, 2, 3, 4]

    # Echtes Ereignisprotokoll mit Korrektur.
    corrected = [s for e in entries for s in e["starts"] if s["status"] == "final"]
    histories = [
        await _get(data_api, f"/tournaments/{tid}/starts/{s['id']}/events") for s in corrected
    ]
    types = Counter(event["type"] for history in histories for event in history)
    assert types["finalized"] == len(corrected)
    assert types["corrected"] == 1


async def test_only_one_practice_tournament(data_api: Api) -> None:
    created = await _practice(data_api)

    second = await data_api.client.post(f"{API}/tournaments/practice")

    assert second.status_code == 409
    assert second.json()["code"] == "practice_exists"
    assert second.json()["tournament_id"] == created["id"]
    assert "Übungsturnier" in second.json()["detail"]
    assert len(await _get(data_api, "/tournaments")) == 1


async def test_remove_practice_leaves_nothing_behind(data_api: Api, engine: AsyncEngine) -> None:
    # Echte Daten daneben.
    real_club = (await data_api.client.post(f"{API}/clubs", json={"name": "SV Echtstadt"})).json()
    real_person = (
        await data_api.client.post(
            f"{API}/persons", json={"name": "Echte Person", "club_id": real_club["id"]}
        )
    ).json()
    real = await data_api.create_tournament(name="Echtes Turnier")
    created = await _practice(data_api)
    tid = created["id"]
    assert await _count(engine, "SELECT count(*) FROM result_event") > 0

    response = await data_api.client.delete(f"{API}/tournaments/{tid}")

    assert response.status_code == 204, response.text
    assert [t["id"] for t in await _get(data_api, "/tournaments")] == [real["id"]]
    items = await _get(data_api, "/persons", limit=100)
    assert [p["id"] for p in items] == [real_person["id"]]
    assert [c["id"] for c in await _get(data_api, "/clubs")] == [real_club["id"]]
    for table in ("result_event", "result_current", "start", "entry", "heat", "competition"):
        assert await _count(engine, f"SELECT count(*) FROM {table}") == 0, table
    assert (
        await _count(
            engine,
            "SELECT count(*) FROM audit_log WHERE details->>'tournament_id' = :tid",
            tid=tid,
        )
        == 0
    )
    assert (
        await _count(
            engine,
            "SELECT count(*) FROM audit_log WHERE action = 'tournament.practice_removed'",
        )
        == 1
    )
    names = [event.name for event in data_api.drain()]
    assert names.count("person.deleted") == 12
    assert names.count("club.deleted") == 3
    assert names[-1] == "tournament.deleted"
    # Danach lässt sich wieder eine Übung anlegen.
    assert (await _practice(data_api))["is_practice"] is True


async def test_remove_practice_keeps_persons_used_elsewhere(data_api: Api) -> None:
    created = await _practice(data_api)
    entries = await _get(data_api, f"/tournaments/{created['id']}/entries")
    person_id = entries[0]["person"]["id"]
    real = await data_api.create_tournament(name="Echtes Turnier")
    klasse = await data_api.create(real["id"], "classes", code="offen", name="Offen", short="O")
    await data_api.create(real["id"], "entries", person_id=person_id, class_id=klasse["id"])

    response = await data_api.client.delete(f"{API}/tournaments/{created['id']}")

    assert response.status_code == 204
    items = await _get(data_api, "/persons", limit=100)
    assert [p["id"] for p in items] == [person_id]
    # Sein Verein bleibt mit ihm.
    assert len(await _get(data_api, "/clubs")) == 1


async def test_real_results_stay_immutable(data_api: Api, engine: AsyncEngine) -> None:
    """Die Ausnahme im Trigger gilt nur für das Übungsturnier."""
    await _practice(data_api)
    real = await data_api.create_tournament(name="Echtes Turnier")
    tid = real["id"]
    stand = await data_api.create(tid, "ranges", name="Stand", lane_count=2)
    klasse = await data_api.create(tid, "classes", code="offen", name="Offen", short="O")
    competition = await data_api.create(
        tid, "competitions", catalog_federation="bds", catalog_code="4401", range_id=stand["id"]
    )
    person = (await data_api.client.post(f"{API}/persons", json={"name": "Echte Person"})).json()
    entry = await data_api.create(tid, "entries", person_id=person["id"], class_id=klasse["id"])
    start = (
        await data_api.client.post(
            f"{API}/tournaments/{tid}/entries/{entry['id']}/starts",
            json={"competition_id": competition["id"]},
        )
    ).json()[0]
    aborted = await data_api.client.post(
        f"{API}/tournaments/{tid}/starts/{start['id']}/abort", json={"abort_reason": "dns"}
    )
    assert aborted.status_code == 200, aborted.text

    for statement in (
        "DELETE FROM result_event WHERE start_id = :sid",
        "UPDATE result_event SET reason = 'x' WHERE start_id = :sid",
    ):
        with pytest.raises(DBAPIError, match="unveränderlich"):
            async with engine.begin() as connection:
                await connection.execute(text(statement), {"sid": start["id"]})
    # Auch im Übungsturnier bleibt UPDATE verboten.
    with pytest.raises(DBAPIError, match="unveränderlich"):
        async with engine.begin() as connection:
            await connection.execute(text("UPDATE result_event SET reason = 'x'"))


async def test_practice_flag_is_fixed(data_api: Api, engine: AsyncEngine) -> None:
    real = await data_api.create_tournament(name="Echtes Turnier")
    created = await _practice(data_api)

    for tid, value in ((real["id"], True), (created["id"], False)):
        with pytest.raises(DBAPIError, match="is_practice"):
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE tournament SET is_practice = :value WHERE id = :tid"),
                    {"value": value, "tid": tid},
                )
    # Die Übung lässt sich trotzdem entfernen.
    assert (await data_api.client.delete(f"{API}/tournaments/{created['id']}")).status_code == 204


async def test_closed_practice_can_be_removed(data_api: Api) -> None:
    created = await _practice(data_api)
    closed = await data_api.client.post(
        f"{API}/tournaments/{created['id']}/status", json={"status": "closed"}
    )
    assert closed.status_code == 200

    assert (await data_api.client.delete(f"{API}/tournaments/{created['id']}")).status_code == 204
    assert await _get(data_api, "/tournaments") == []


async def test_failed_practice_is_rolled_back_completely(
    data_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = load_practice().model_copy(deep=True)
    broken.persons[-1].class_code = "gibt-es-nicht"
    monkeypatch.setattr(practice, "load_practice", lambda: broken)

    response = await data_api.client.post(f"{API}/tournaments/practice")

    assert response.status_code == 422
    assert "gibt-es-nicht" in response.json()["detail"]
    assert await _get(data_api, "/tournaments") == []
    assert await _get(data_api, "/persons") == []
    assert await _get(data_api, "/clubs") == []
