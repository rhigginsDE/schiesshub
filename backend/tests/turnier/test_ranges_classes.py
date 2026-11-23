"""Stände und Klassen eines Turniers."""

import uuid

from tests.turnier.conftest import API, Api

# --- Stände ------------------------------------------------------------------


async def test_range_crud(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    api.drain()

    created = await api.create(tid, "ranges", name="25-m-Stand", lane_count=6)
    assert created == {
        "id": created["id"],
        "tournament_id": tid,
        "name": "25-m-Stand",
        "lane_count": 6,
        "sort": 0,
    }
    second = await api.create(tid, "ranges", name="50-m-Stand", lane_count=3)
    assert second["sort"] == 1

    url = f"{API}/tournaments/{tid}/ranges/{created['id']}"
    changed = await api.client.patch(url, json={"lane_count": 8})
    assert changed.status_code == 200
    assert changed.json()["lane_count"] == 8
    assert (await api.client.get(url)).json() == changed.json()

    assert (await api.client.delete(url)).status_code == 204
    assert (await api.client.get(url)).status_code == 404
    listed = await api.client.get(f"{API}/tournaments/{tid}/ranges")
    assert [r["id"] for r in listed.json()] == [second["id"]]

    assert [e.name for e in api.drain()] == [
        "range.created",
        "range.created",
        "range.updated",
        "range.deleted",
    ]


async def test_lane_count_must_be_at_least_one(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]

    create = await api.client.post(
        f"{API}/tournaments/{tid}/ranges", json={"name": "Stand", "lane_count": 0}
    )
    range_ = await api.create(tid, "ranges", name="Stand", lane_count=1)
    update = await api.client.patch(
        f"{API}/tournaments/{tid}/ranges/{range_['id']}", json={"lane_count": 0}
    )

    assert create.status_code == 422
    assert create.json() == {
        "detail": "Feld ‚lane_count‘: muss mindestens 1 sein.",
        "errors": [{"field": "lane_count", "message": "muss mindestens 1 sein"}],
    }
    assert update.status_code == 422


async def test_range_of_another_tournament_is_not_found(api: Api) -> None:
    first = await api.create_tournament()
    second = await api.create_tournament()
    range_ = await api.create(first["id"], "ranges", name="Stand", lane_count=2)

    response = await api.client.get(f"{API}/tournaments/{second['id']}/ranges/{range_['id']}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Der Schießstand wurde in diesem Turnier nicht gefunden."}


async def test_reorder_ranges(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    ids = [(await api.create(tid, "ranges", name=n, lane_count=1))["id"] for n in "ABC"]
    api.drain()

    new_order = [ids[2], ids[0], ids[1]]
    response = await api.client.put(
        f"{API}/tournaments/{tid}/ranges/order", json={"ids": new_order}
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == new_order
    assert [r["sort"] for r in response.json()] == [0, 1, 2]
    listed = await api.client.get(f"{API}/tournaments/{tid}/ranges")
    assert [r["id"] for r in listed.json()] == new_order
    assert [e.name for e in api.drain()] == ["range.reordered"]


async def test_reorder_needs_every_entry_exactly_once(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    ids = [(await api.create(tid, "ranges", name=n, lane_count=1))["id"] for n in "AB"]

    for wrong in ([ids[0]], [ids[0], ids[0]], [*ids, str(uuid.uuid4())]):
        response = await api.client.put(
            f"{API}/tournaments/{tid}/ranges/order", json={"ids": wrong}
        )
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Die neue Reihenfolge muss jeden Eintrag des Turniers genau einmal enthalten."
        )


# --- Klassen -----------------------------------------------------------------


async def test_class_crud(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    api.drain()

    open_class = await api.create(tid, "classes", code="offen", name="Offene Klasse", short="O")
    ladies = await api.create(
        tid, "classes", code="damen", name="Damen", short="D", merge_into_id=open_class["id"]
    )
    assert ladies["merge_into_id"] == open_class["id"]
    assert ladies["sort"] == 1

    url = f"{API}/tournaments/{tid}/classes/{ladies['id']}"
    changed = await api.client.patch(url, json={"name": "Damenklasse", "merge_into_id": None})
    assert changed.status_code == 200
    assert changed.json()["name"] == "Damenklasse"
    assert changed.json()["merge_into_id"] is None

    assert (await api.client.delete(url)).status_code == 204
    listed = await api.client.get(f"{API}/tournaments/{tid}/classes")
    assert [c["code"] for c in listed.json()] == ["offen"]
    assert [e.name for e in api.drain()] == [
        "class.created",
        "class.created",
        "class.updated",
        "class.deleted",
    ]


async def test_class_code_is_unique_per_tournament(api: Api) -> None:
    first = await api.create_tournament()
    second = await api.create_tournament()
    await api.create(first["id"], "classes", code="offen", name="Offen", short="O")
    await api.create(second["id"], "classes", code="offen", name="Offen", short="O")

    response = await api.client.post(
        f"{API}/tournaments/{first['id']}/classes",
        json={"code": "offen", "name": "Noch einmal", "short": "O2"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Eine Klasse mit dem Kürzel „offen“ gibt es in diesem Turnier schon."
    }


async def test_merge_must_not_form_a_cycle(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    a = await api.create(tid, "classes", code="a", name="A", short="A")
    b = await api.create(tid, "classes", code="b", name="B", short="B", merge_into_id=a["id"])
    c = await api.create(tid, "classes", code="c", name="C", short="C", merge_into_id=b["id"])

    cycle = await api.client.patch(
        f"{API}/tournaments/{tid}/classes/{a['id']}", json={"merge_into_id": c["id"]}
    )
    itself = await api.client.patch(
        f"{API}/tournaments/{tid}/classes/{a['id']}", json={"merge_into_id": a["id"]}
    )
    foreign = await api.client.post(
        f"{API}/tournaments/{tid}/classes",
        json={"code": "d", "name": "D", "short": "D", "merge_into_id": str(uuid.uuid4())},
    )

    assert cycle.status_code == 422
    assert cycle.json()["detail"].startswith("Diese Zusammenlegung ergäbe einen Kreis")
    assert itself.status_code == 422
    assert foreign.status_code == 422
    assert foreign.json()["detail"] == (
        "Die Zielklasse der Zusammenlegung gehört nicht zu diesem Turnier."
    )


async def test_deleting_a_class_removes_it_from_competitions(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    keep = await api.create(tid, "classes", code="offen", name="Offen", short="O")
    drop = await api.create(
        tid, "classes", code="damen", name="Damen", short="D", merge_into_id=keep["id"]
    )
    child = await api.create(
        tid, "classes", code="jugend", name="Jugend", short="J", merge_into_id=drop["id"]
    )
    competition = await api.create(
        tid,
        "competitions",
        catalog_federation="bds",
        catalog_code="1001",
        class_ids=[keep["id"], drop["id"]],
    )

    await api.client.delete(f"{API}/tournaments/{tid}/classes/{drop['id']}")

    fetched = await api.client.get(f"{API}/tournaments/{tid}/competitions/{competition['id']}")
    assert fetched.json()["class_ids"] == [keep["id"]]
    orphan = await api.client.get(f"{API}/tournaments/{tid}/classes/{child['id']}")
    assert orphan.json()["merge_into_id"] is None


async def test_import_classes_from_catalog(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    await api.create(tid, "classes", code="gast", name="Gäste", short="G")
    api.drain()

    response = await api.client.post(
        f"{API}/tournaments/{tid}/classes/import", json={"federation": "bds"}
    )

    assert response.status_code == 201
    imported = response.json()
    catalog = (await api.client.get(f"{API}/katalog/klassen", params={"verband": "bds"})).json()
    assert [c["code"] for c in imported] == [k["id"] for k in catalog]
    assert [c["short"] for c in imported] == [k["kurz"] for k in catalog]
    # Nach der schon vorhandenen Klasse einsortiert.
    assert [c["sort"] for c in imported] == list(range(1, len(catalog) + 1))

    by_code = {c["code"]: c for c in imported}
    by_id = {c["id"]: c["code"] for c in imported}
    merges = {code: by_id.get(c["merge_into_id"]) for code, c in by_code.items()}
    # Genau ein Ziel im Katalog: übernommen.
    assert merges["jugend-1"] == "jugend-2"
    assert merges["damen-2"] == "damen-1"
    assert merges["alters"] == "schuetzen"
    # Mehrere Ziele, nach Alter oder keines: Entscheidung der Turnierleitung.
    assert merges["jugend-2"] is None
    assert merges["damen-1"] is None
    assert merges["senioren"] is None
    assert merges["schuetzen"] is None

    events = api.drain()
    assert [e.name for e in events] == ["class.imported"]
    assert sorted(events[0].data["class_ids"]) == sorted(by_id)


async def test_import_twice_creates_no_duplicates(api: Api) -> None:
    tournament = await api.create_tournament()
    url = f"{API}/tournaments/{tournament['id']}/classes/import"
    first = await api.client.post(url, json={"federation": "bds"})

    second = await api.client.post(url, json={"federation": "bds"})

    assert second.status_code == 201
    assert second.json() == []
    listed = await api.client.get(f"{API}/tournaments/{tournament['id']}/classes")
    assert len(listed.json()) == len(first.json())


async def test_import_unknown_federation(api: Api) -> None:
    tournament = await api.create_tournament()

    response = await api.client.post(
        f"{API}/tournaments/{tournament['id']}/classes/import", json={"federation": "xyz"}
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Der Verband „xyz“ ist im Katalog nicht vorhanden."}
