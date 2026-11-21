"""Wettbewerbe: aus dem Katalog, eigene, Ändern, Zurücksetzen, Sortieren, Löschen."""

import copy
import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import ClientFactory, edit_yaml
from tests.turnier.conftest import API, Api

PRAEZISION_VARIANT = {
    "id": "standard",
    "name": "Standard",
    "abschnitte": [
        {
            "id": "praezision",
            "name": "Präzision",
            "serien": 2,
            "schuss_je_serie": 10,
            "zeit_je_serie_s": 300,
        }
    ],
}


def own_definition() -> dict[str, Any]:
    return {
        "variant": {
            "id": "vereinsrunde",
            "name": "Vereinsrunde",
            "abschnitte": [
                {"id": "probe", "name": "Probe", "serien": 1, "schuss_je_serie": 5},
                {"id": "wertung", "name": "Wertung", "serien": 3, "schuss_je_serie": 10},
            ],
        },
        "scoring": {"modell": "ringe", "rangfolge": "absteigend", "geprueft": False},
    }


async def tournament_with_range(api: Api, **settings: Any) -> tuple[str, str]:
    tournament = await api.create_tournament(settings=settings or None)
    range_ = await api.create(tournament["id"], "ranges", name="Stand 1", lane_count=6)
    api.drain()
    return tournament["id"], range_["id"]


# --- Aus dem Katalog ---------------------------------------------------------


async def test_from_catalog_precision_is_scheduled(api: Api) -> None:
    tid, range_id = await tournament_with_range(
        api, default_changeover_minutes=4, default_fee_first_cents=1000
    )

    competition = await api.create(
        tid, "competitions", catalog_federation="bds", catalog_code="1001", range_id=range_id
    )

    assert competition["name"] == "Pistole bis 9 mm"
    assert competition["catalog_federation"] == "bds"
    assert competition["catalog_code"] == "1001"
    assert competition["range_id"] == range_id
    assert competition["definition"] == {
        "source": {
            "federation": "bds",
            "code": "1001",
            "group": "kw-25m-praezision",
            "catalog_stand": "2026-06-30",
        },
        "variant": PRAEZISION_VARIANT,
        "scoring": {
            "modell": "ringe",
            "rangfolge": "absteigend",
            "geprueft": True,
            "gleichstand": ["zehner", "innenzehner", "neuner_abwaerts"],
        },
        "ablauf_beschreibung": "20 Schuss: 2×10 in je 5 Min.",
    }
    # 2 × 300 s = 10 Minuten Schießzeit plus 4 Minuten Wechsel.
    assert competition["planning"] == "schedule"
    assert competition["heat_minutes"] == 14
    assert competition["changeover_minutes"] == 4
    assert competition["fee_first_cents"] == 1000
    assert competition["fee_repeat_cents"] == 0
    assert competition["capture_mode"] == "series"
    assert competition["class_ids"] == []
    assert [(e.name, e.data) for e in api.drain()] == [
        ("competition.created", {"tournament_id": tid, "competition_id": competition["id"]})
    ]


async def test_from_catalog_falling_plate_is_a_queue(api: Api) -> None:
    tid, _ = await tournament_with_range(api)

    competition = await api.create(
        tid, "competitions", catalog_federation="bds", catalog_code="4401"
    )

    assert competition["planning"] == "queue"
    assert competition["heat_minutes"] is None
    assert competition["changeover_minutes"] == 5
    assert competition["definition"]["source"]["group"] == "flinte-15m-fallscheibe"
    assert competition["definition"]["scoring"]["modell"] == "zeit_plus_zuschlaege"
    section = competition["definition"]["variant"]["abschnitte"][0]
    # Nur die Kernwerte prüfen: Der Katalog darf weitere Felder ergänzen.
    assert (
        section.items()
        >= {
            "id": "fallscheibe",
            "serien": 4,
            "ziele_je_serie": 5,
            "max_schuss_je_serie": 6,
            "max_zeit_je_serie_s": 60,
            "zeit_wird_gemessen": True,
            "zuschlag_je_stehender_scheibe_s": 10,
        }.items()
    )


async def test_given_values_override_defaults(api: Api) -> None:
    tid, _ = await tournament_with_range(api)

    competition = await api.create(
        tid,
        "competitions",
        catalog_federation="bds",
        catalog_code="4401",
        name="Flinte Pokal",
        planning="schedule",
        heat_minutes=12,
        capture_mode="shot",
        multi_start=True,
        max_starts=2,
        multi_start_rule="all",
        fee_first_cents=800,
        fee_repeat_cents=500,
        combined_ranking=True,
    )

    assert competition["name"] == "Flinte Pokal"
    assert (competition["planning"], competition["heat_minutes"]) == ("schedule", 12)
    assert competition["capture_mode"] == "shot"
    assert (competition["multi_start"], competition["max_starts"]) == (True, 2)
    assert competition["multi_start_rule"] == "all"
    assert (competition["fee_first_cents"], competition["fee_repeat_cents"]) == (800, 500)
    assert competition["combined_ranking"] is True


async def test_choose_variant(api: Api) -> None:
    tid, _ = await tournament_with_range(api)
    detail = (await api.client.get(f"{API}/katalog/disziplinen/bds/1001")).json()
    variant_ids = [v["id"] for v in detail["ablauf"]["varianten"]]

    competition = await api.create(
        tid,
        "competitions",
        catalog_federation="bds",
        catalog_code="1001",
        variant_id=variant_ids[-1],
    )

    assert competition["definition"]["variant"]["id"] == variant_ids[-1]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            {"catalog_federation": "bds", "catalog_code": "9999"},
            "Die Disziplin mit der Kennziffer „9999“ gibt es im Katalog des Verbands „bds“ nicht.",
        ),
        (
            {"catalog_federation": "xyz", "catalog_code": "1001"},
            "Der Verband „xyz“ ist im Katalog nicht vorhanden.",
        ),
        (
            {"catalog_federation": "bds", "catalog_code": "1001", "variant_id": "dm"},
            "Die Variante „dm“ gibt es für die Kennziffer „1001“ nicht. Vorhanden: „standard“.",
        ),
    ],
)
async def test_unknown_catalog_entries(api: Api, body: dict, message: str) -> None:
    tid, _ = await tournament_with_range(api)

    response = await api.client.post(f"{API}/tournaments/{tid}/competitions", json=body)

    assert response.status_code == 422
    assert response.json() == {"detail": message}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"catalog_federation": "bds"},
        {"catalog_federation": "bds", "catalog_code": "1001", "definition": own_definition()},
        {"definition": own_definition()},  # ohne Namen
        {"name": "X", "definition": own_definition(), "variant_id": "standard"},
        {
            "catalog_federation": "bds",
            "catalog_code": "1001",
            "multi_start": False,
            "max_starts": 2,
        },
        {"catalog_federation": "bds", "catalog_code": "1001", "max_starts": 0},
        {"catalog_federation": "bds", "catalog_code": "1001", "fee_first_cents": -1},
        {"catalog_federation": "bds", "catalog_code": "1001", "planning": "irgendwann"},
        {"catalog_federation": "bds", "catalog_code": "1001", "farbe": "rot"},
    ],
)
async def test_invalid_create_bodies(api: Api, body: dict) -> None:
    tid, _ = await tournament_with_range(api)

    response = await api.client.post(f"{API}/tournaments/{tid}/competitions", json=body)

    assert response.status_code == 422, response.text


async def test_schedule_without_duration_is_rejected(api: Api) -> None:
    tid, _ = await tournament_with_range(api)

    response = await api.client.post(
        f"{API}/tournaments/{tid}/competitions",
        json={"catalog_federation": "bds", "catalog_code": "4401", "planning": "schedule"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Für einen Zeitplan wird die Dauer eines Durchgangs (heat_minutes) benötigt."
    }


async def test_range_and_classes_must_belong_to_the_tournament(api: Api) -> None:
    tid, _ = await tournament_with_range(api)
    other_tid, other_range = await tournament_with_range(api)
    other_class = await api.create(other_tid, "classes", code="o", name="O", short="O")
    base = {"catalog_federation": "bds", "catalog_code": "1001"}

    foreign_range = await api.client.post(
        f"{API}/tournaments/{tid}/competitions", json={**base, "range_id": other_range}
    )
    unknown_range = await api.client.post(
        f"{API}/tournaments/{tid}/competitions", json={**base, "range_id": str(uuid.uuid4())}
    )
    foreign_class = await api.client.post(
        f"{API}/tournaments/{tid}/competitions", json={**base, "class_ids": [other_class["id"]]}
    )

    assert foreign_range.status_code == 422
    assert foreign_range.json()["detail"] == "Der angegebene Stand gehört nicht zu diesem Turnier."
    assert unknown_range.status_code == 422
    assert foreign_class.status_code == 422
    assert foreign_class.json()["detail"] == (
        "Mindestens eine der angegebenen Klassen gehört nicht zum Turnier."
    )


# --- Eigene Wettbewerbe ------------------------------------------------------


async def test_own_competition_without_catalog(api: Api) -> None:
    tid, _ = await tournament_with_range(api)

    competition = await api.create(
        tid, "competitions", name="Vereinsrunde", definition=own_definition()
    )

    assert competition["catalog_federation"] is None
    assert competition["catalog_code"] is None
    assert competition["definition"] == own_definition()
    assert competition["planning"] == "queue"


async def test_own_definition_is_validated_like_the_catalog(api: Api) -> None:
    tid, _ = await tournament_with_range(api)
    broken_list = own_definition()
    broken_list["variant"]["abschnitte"][1]["zeiten_s"] = [30, 30]
    unknown_field = own_definition()
    unknown_field["scoring"]["bonus"] = 3
    duplicate_section = own_definition()
    duplicate_section["variant"]["abschnitte"][1]["id"] = "probe"
    with_source = own_definition()
    with_source["source"] = {
        "federation": "bds",
        "code": "1001",
        "group": "kw-25m-praezision",
        "catalog_stand": "2026-06-30",
    }

    for definition in (broken_list, unknown_field, duplicate_section, with_source):
        response = await api.client.post(
            f"{API}/tournaments/{tid}/competitions", json={"name": "X", "definition": definition}
        )
        assert response.status_code == 422, definition


# --- Ändern, Zurücksetzen, Katalog-Update ------------------------------------


async def test_update_fields(api: Api) -> None:
    tid, range_id = await tournament_with_range(api, default_multi_start=True, default_max_starts=3)
    klass = await api.create(tid, "classes", code="offen", name="Offen", short="O")
    competition = await api.create(
        tid, "competitions", catalog_federation="bds", catalog_code="1001"
    )
    assert (competition["multi_start"], competition["max_starts"]) == (True, 3)
    url = f"{API}/tournaments/{tid}/competitions/{competition['id']}"
    api.drain()

    response = await api.client.patch(
        url,
        json={
            "name": "Pistole 9 mm",
            "range_id": range_id,
            "class_ids": [klass["id"]],
            "multi_start": False,
            "heat_minutes": 20,
            "fee_first_cents": 700,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Pistole 9 mm"
    assert body["range_id"] == range_id
    assert body["class_ids"] == [klass["id"]]
    # Ohne Mehrfachstart bleibt genau ein Start.
    assert (body["multi_start"], body["max_starts"]) == (False, 1)
    assert body["heat_minutes"] == 20
    assert body["fee_first_cents"] == 700
    assert (await api.client.get(url)).json() == body
    assert [e.name for e in api.drain()] == ["competition.updated"]

    cleared = await api.client.patch(url, json={"range_id": None, "planning": "queue"})
    assert cleared.json()["range_id"] is None
    assert cleared.json()["planning"] == "queue"

    for invalid in (
        {"name": None},
        {"max_starts": 2},
        {"heat_minutes": None, "planning": "schedule"},
    ):
        refused = await api.client.patch(url, json=invalid)
        assert refused.status_code == 422, invalid
    assert (await api.client.get(url)).json() == cleared.json()


async def test_update_definition_keeps_source(api: Api) -> None:
    tid, _ = await tournament_with_range(api)
    competition = await api.create(
        tid, "competitions", catalog_federation="bds", catalog_code="1001"
    )
    url = f"{API}/tournaments/{tid}/competitions/{competition['id']}"
    changed = copy.deepcopy(competition["definition"])
    del changed["source"]
    changed["variant"]["abschnitte"][0]["serien"] = 3

    response = await api.client.patch(url, json={"definition": changed})

    assert response.status_code == 200
    definition = response.json()["definition"]
    assert definition["variant"]["abschnitte"][0]["serien"] == 3
    assert definition["source"] == competition["definition"]["source"]

    moved = copy.deepcopy(competition["definition"])
    moved["source"]["code"] = "1002"
    refused = await api.client.patch(url, json={"definition": moved})
    assert refused.status_code == 422


async def test_reset_definition(api: Api) -> None:
    tid, _ = await tournament_with_range(api)
    competition = await api.create(
        tid, "competitions", catalog_federation="bds", catalog_code="1001"
    )
    url = f"{API}/tournaments/{tid}/competitions/{competition['id']}"
    changed = copy.deepcopy(competition["definition"])
    changed["scoring"]["geprueft"] = False
    await api.client.patch(url, json={"definition": changed, "heat_minutes": 30})
    api.drain()

    response = await api.client.post(f"{url}/reset-definition")

    assert response.status_code == 200
    assert response.json()["definition"] == competition["definition"]
    # Nur die Definition wird zurückgesetzt.
    assert response.json()["heat_minutes"] == 30
    assert [e.name for e in api.drain()] == ["competition.updated"]


async def test_reset_without_catalog_origin(api: Api) -> None:
    tid, _ = await tournament_with_range(api)
    competition = await api.create(tid, "competitions", name="Eigen", definition=own_definition())

    response = await api.client.post(
        f"{API}/tournaments/{tid}/competitions/{competition['id']}/reset-definition"
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Dieser Wettbewerb stammt nicht aus dem Katalog und hat deshalb keinen "
        "Katalogwert."
    }


async def test_copy_stays_when_the_catalog_changes(
    start_app: ClientFactory, catalog_copy: Path
) -> None:
    group_file = catalog_copy / "bds" / "gruppen" / "kw-25m-praezision.yaml"
    async with start_app(catalog_copy) as client:
        tournament = await client.post(
            f"{API}/tournaments", json={"name": "Pokal", "date_from": "2027-05-01"}
        )
        tid = tournament.json()["id"]
        created = await client.post(
            f"{API}/tournaments/{tid}/competitions",
            json={"catalog_federation": "bds", "catalog_code": "1001"},
        )
        original = created.json()

    def change(data: dict) -> None:
        data["ablaeufe"]["praezision-2x10"]["varianten"][0]["abschnitte"][0]["zeit_je_serie_s"] = (
            240
        )
        data["wertung"]["geprueft"] = False

    edit_yaml(group_file, change)

    async with start_app(catalog_copy) as client:
        url = f"{API}/tournaments/{tid}/competitions/{original['id']}"
        after_update = (await client.get(url)).json()
        reset = (await client.post(f"{url}/reset-definition")).json()

    assert after_update == original
    assert after_update["definition"]["variant"] == PRAEZISION_VARIANT
    section = reset["definition"]["variant"]["abschnitte"][0]
    assert section["zeit_je_serie_s"] == 240
    assert reset["definition"]["scoring"]["geprueft"] is False


# --- Sortieren und Löschen ---------------------------------------------------


async def test_sort_and_delete(api: Api) -> None:
    tid, _ = await tournament_with_range(api)
    ids = [
        (await api.create(tid, "competitions", catalog_federation="bds", catalog_code=code))["id"]
        for code in ("1001", "1002", "4401")
    ]
    api.drain()

    reordered = await api.client.put(
        f"{API}/tournaments/{tid}/competitions/order", json={"ids": ids[::-1]}
    )
    assert [c["id"] for c in reordered.json()] == ids[::-1]

    deleted = await api.client.delete(f"{API}/tournaments/{tid}/competitions/{ids[1]}")
    assert deleted.status_code == 204
    listed = await api.client.get(f"{API}/tournaments/{tid}/competitions")
    assert [c["id"] for c in listed.json()] == [ids[2], ids[0]]
    assert [(e.name, e.data) for e in api.drain()] == [
        ("competition.reordered", {"tournament_id": tid}),
        ("competition.deleted", {"tournament_id": tid, "competition_id": ids[1]}),
    ]


async def test_deleting_a_range_keeps_its_competitions(api: Api) -> None:
    tid, range_id = await tournament_with_range(api)
    competition = await api.create(
        tid, "competitions", catalog_federation="bds", catalog_code="1001", range_id=range_id
    )

    await api.client.delete(f"{API}/tournaments/{tid}/ranges/{range_id}")

    fetched = await api.client.get(f"{API}/tournaments/{tid}/competitions/{competition['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["range_id"] is None
