"""Anmeldungen: Startnummern, Klassen, Suche, Ändern, Löschen, Sperre, Löschschutz, Audit."""

from sqlalchemy import select

from app.modules.auth.models import AuditLog
from tests.starts.conftest import Api, Setup


async def test_start_numbers_from_tournament_setting_and_manual_override(api: Api) -> None:
    tid = await api.tournament(first_start_number=100)
    class_id = await api.klass(tid)

    first = await api.entry(tid, class_id)
    manual = await api.entry(tid, class_id, start_number=102)
    third = await api.entry(tid, class_id)
    fourth = await api.entry(tid, class_id)

    assert [first["start_number"], manual["start_number"]] == [100, 102]
    # Die nächste freie Nummer: 101, dann über die vergebene 102 hinweg 103.
    assert [third["start_number"], fourth["start_number"]] == [101, 103]
    detail = await api.fail(
        "POST",
        f"/tournaments/{tid}/entries",
        409,
        json={"person_id": await api.person(), "class_id": class_id, "start_number": 100},
    )
    assert detail == "Die Startnummer 100 ist in diesem Turnier schon vergeben."


async def test_default_start_number_is_one(api: Api, queue_setup: Setup) -> None:
    entry = await api.entry(queue_setup.tid, queue_setup.class_id)
    assert entry["start_number"] == 1
    assert entry["person"]["name"].startswith("Person")
    assert entry["starts"] == []
    assert entry["fee_total_cents"] == 0
    names = [event.name for event in api.drain()]
    assert "entry.created" in names


async def test_person_only_once_per_tournament(api: Api, queue_setup: Setup) -> None:
    person = await api.person("Anna Schmidt")
    await api.entry(queue_setup.tid, queue_setup.class_id, person)
    detail = await api.fail(
        "POST",
        f"/tournaments/{queue_setup.tid}/entries",
        409,
        json={"person_id": person, "class_id": queue_setup.class_id},
    )
    assert detail == "Diese Person ist in diesem Turnier schon angemeldet (Startnummer 1)."
    # In einem anderen Turnier geht es.
    other = await api.tournament()
    await api.entry(other, await api.klass(other), person)


async def test_class_must_belong_to_tournament(api: Api, queue_setup: Setup) -> None:
    other = await api.tournament()
    foreign_class = await api.klass(other)
    response = await api.client.post(
        f"/api/v1/tournaments/{queue_setup.tid}/entries",
        json={"person_id": await api.person(), "class_id": foreign_class},
    )
    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"field": "class_id", "message": "Die Klasse gehört nicht zu diesem Turnier."}
    ]


async def test_unknown_person_and_strict_input(api: Api, queue_setup: Setup) -> None:
    path = f"/tournaments/{queue_setup.tid}/entries"
    detail = await api.fail(
        "POST",
        path,
        422,
        json={
            "person_id": "00000000-0000-0000-0000-000000000000",
            "class_id": queue_setup.class_id,
        },
    )
    assert detail == "Diese Person gibt es nicht."
    await api.fail(
        "POST",
        path,
        422,
        json={"person_id": await api.person(), "class_id": queue_setup.class_id, "x": 1},
    )
    await api.fail(
        "POST",
        path,
        422,
        json={
            "person_id": await api.person(),
            "class_id": queue_setup.class_id,
            "start_number": "5",
        },
    )


async def test_search_by_start_number_and_name(api: Api, queue_setup: Setup) -> None:
    tid, class_id = queue_setup.tid, queue_setup.class_id
    club = await api.club("SV Grünwald")
    anna = await api.entry(tid, class_id, await api.person("Anna Köhler", club_id=club))
    bernd = await api.entry(tid, class_id, await api.person("Bernd Brandt"), start_number=12)
    await api.entry(tid, class_id, await api.person("Carla Zehner"))

    async def search(q: str) -> list[int]:
        found = await api.ok("GET", f"/tournaments/{tid}/entries", params={"q": q})
        return [item["start_number"] for item in found]

    assert await search("") == [1, 2, 12]
    assert await search("12") == [12]
    assert await search("koehler") == [anna["start_number"]]
    assert await search("grünwald") == [anna["start_number"]]
    assert await search("br") == [bernd["start_number"]]
    assert await search("nobody") == []
    found = await api.ok("GET", f"/tournaments/{tid}/entries", params={"q": "anna"})
    assert found[0]["person"] == {
        "id": anna["person"]["id"],
        "name": "Anna Köhler",
        "display_name": "Anna Köhler",
        "club": "SV Grünwald",
    }


async def test_update_class_and_number(api: Api, queue_setup: Setup) -> None:
    tid = queue_setup.tid
    juniors = await api.klass(tid, "junioren", "Junioren")
    restricted = await api.competition(tid, None, "Nur Offen", class_ids=[queue_setup.class_id])
    entry = await api.entry(tid, queue_setup.class_id)
    other = await api.entry(tid, queue_setup.class_id)
    path = f"/tournaments/{tid}/entries/{entry['id']}"

    changed = await api.ok("PATCH", path, json={"start_number": 7})
    assert changed["start_number"] == 7
    detail = await api.fail("PATCH", path, 409, json={"start_number": other["start_number"]})
    assert "schon vergeben" in detail
    await api.fail("PATCH", path, 422, json={"start_number": None})

    await api.book(tid, entry["id"], restricted["id"])
    detail = await api.fail("PATCH", path, 409, json={"class_id": juniors})
    assert detail.startswith("Die Klasse „Junioren“ ist in „Nur Offen“ nicht zugelassen")
    # Ohne Starts im eingeschränkten Wettbewerb ist der Wechsel möglich.
    changed = await api.ok(
        "PATCH", f"/tournaments/{tid}/entries/{other['id']}", json={"class_id": juniors}
    )
    assert changed["class_id"] == juniors


async def test_delete_only_without_shot_starts(api: Api, queue_setup: Setup) -> None:
    tid, cid = queue_setup.tid, queue_setup.competition_id
    keep = await api.entry(tid, queue_setup.class_id)
    gone = await api.entry(tid, queue_setup.class_id)
    await api.book(tid, gone["id"], cid)
    shot = await api.book(tid, keep["id"], cid)
    await api.ok("POST", f"/tournaments/{tid}/starts/{shot[0]['id']}/call", json={})

    detail = await api.fail("DELETE", f"/tournaments/{tid}/entries/{keep['id']}", 409)
    assert "nicht löschen" in detail
    await api.ok("DELETE", f"/tournaments/{tid}/entries/{gone['id']}", 204)
    await api.fail("GET", f"/tournaments/{tid}/entries/{gone['id']}", 404)
    queue = await api.ok("GET", f"/tournaments/{tid}/ranges/{queue_setup.range_id}/queue")
    assert queue["waiting"] == []


async def test_closed_tournament_is_locked(api: Api, queue_setup: Setup) -> None:
    tid = queue_setup.tid
    entry = await api.entry(tid, queue_setup.class_id)
    start = (await api.book(tid, entry["id"], queue_setup.competition_id))[0]
    await api.set_status(tid, "active", "closed")

    locked = "Das Turnier ist abgeschlossen"
    calls = [
        (
            "POST",
            f"/tournaments/{tid}/entries",
            {"person_id": await api.person(), "class_id": queue_setup.class_id},
        ),
        ("PATCH", f"/tournaments/{tid}/entries/{entry['id']}", {"start_number": 9}),
        ("DELETE", f"/tournaments/{tid}/entries/{entry['id']}", None),
        (
            "POST",
            f"/tournaments/{tid}/entries/{entry['id']}/starts",
            {"competition_id": queue_setup.competition_id},
        ),
        ("DELETE", f"/tournaments/{tid}/starts/{start['id']}", None),
        ("POST", f"/tournaments/{tid}/starts/{start['id']}/call", {}),
        ("POST", f"/tournaments/{tid}/starts/{start['id']}/abort", {"abort_reason": "dns"}),
        ("POST", f"/tournaments/{tid}/starts/{start['id']}/move", {"position": 1}),
        ("POST", f"/tournaments/{tid}/ranges/{queue_setup.range_id}/call-next", None),
    ]
    for method, path, body in calls:
        detail = await api.fail(method, path, 409, json=body)
        assert detail.startswith(locked), (method, path, detail)
    # Lesen geht weiter.
    await api.ok("GET", f"/tournaments/{tid}/entries/{entry['id']}")
    await api.ok("GET", f"/tournaments/{tid}/startlist")


async def test_person_with_entry_cannot_be_deleted(api: Api, queue_setup: Setup) -> None:
    person = await api.person("Dora Deich")
    entry = await api.entry(queue_setup.tid, queue_setup.class_id, person)
    detail = await api.fail("DELETE", f"/persons/{person}", 409)
    assert detail == "Die Person ist im Turnier „Vereinspokal“ angemeldet."

    await api.ok("DELETE", f"/tournaments/{queue_setup.tid}/entries/{entry['id']}", 204)
    await api.ok("DELETE", f"/persons/{person}", 204)


async def test_audit_and_events_carry_ids_only(api: Api, queue_setup: Setup) -> None:
    person = await api.person("Erich Geheim")
    entry = await api.entry(queue_setup.tid, queue_setup.class_id, person)
    await api.book(queue_setup.tid, entry["id"], queue_setup.competition_id)
    for event in api.drain():
        assert "Geheim" not in event.encode()
    async with api.app.state.session_factory() as session:
        actions = list(await session.scalars(select(AuditLog.action).order_by(AuditLog.at)))
        details = [entry.details for entry in await session.scalars(select(AuditLog))]
    assert {"entry.created", "start.booked"} <= set(actions)
    assert "Geheim" not in str(details)
