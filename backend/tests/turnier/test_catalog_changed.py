"""Vermerk „Katalog seit der Übernahme geändert“ an jedem Wettbewerb (`catalog_changed`).

Verglichen wird die Katalogfassung, aus der die Definition stammt (`catalog_base`), mit dem
aktuellen Katalog – nicht die Definition selbst: Eine bewusste Abweichung im Turnier ist keine
Änderung des Katalogs.
"""

import copy
from pathlib import Path
from typing import Any

import httpx

from tests.conftest import ClientFactory, edit_yaml
from tests.turnier.conftest import API, Api

GROUP = Path("bds") / "gruppen" / "flinte-15m-fallscheibe.yaml"


async def _ok(client: httpx.AsyncClient, method: str, path: str, status: int = 200, **kw: Any):
    response = await client.request(method, f"{API}{path}", **kw)
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _more_targets(data: dict) -> None:
    data["ablaeufe"]["fallscheibe-max6"]["varianten"][0]["abschnitte"][0]["serien"] = 5


async def test_fresh_and_own_competitions_are_unchanged(api: Api) -> None:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    catalog = await api.create(tid, "competitions", catalog_federation="bds", catalog_code="4401")
    own = await api.create(
        tid,
        "competitions",
        name="Eigener",
        definition={k: v for k, v in catalog["definition"].items() if k != "source"},
    )

    assert catalog["catalog_changed"] is False
    stand = catalog["definition"]["source"]["catalog_stand"]
    assert catalog["catalog_stand_then"] == catalog["catalog_stand_now"] == stand
    assert own["catalog_changed"] is False
    assert own["catalog_stand_then"] is None
    assert own["catalog_stand_now"] is None

    # Eine bewusste Abweichung ist keine Katalogänderung.
    definition = copy.deepcopy(catalog["definition"])
    definition["variant"]["abschnitte"][0]["serien_gewertet"] = 3
    patched = await _ok(
        api.client,
        "PATCH",
        f"/tournaments/{tid}/competitions/{catalog['id']}",
        json={"definition": definition},
    )
    assert patched["catalog_changed"] is False
    overview = await _ok(api.client, "GET", f"/tournaments/{tid}/overview")
    assert [c["catalog_changed"] for c in overview["competitions"]] == [False, False]


async def test_catalog_change_is_flagged_everywhere_until_taken_over(
    start_app: ClientFactory, catalog_copy: Path
) -> None:
    async with start_app(catalog_copy) as client:
        tournament = await _ok(
            client, "POST", "/tournaments", 201, json={"name": "VM", "date_from": "2026-05-01"}
        )
        tid = tournament["id"]
        competition = await _ok(
            client,
            "POST",
            f"/tournaments/{tid}/competitions",
            201,
            json={"catalog_federation": "bds", "catalog_code": "4401"},
        )
        # Bewusste Abweichung vor der Katalogänderung: bleibt unberührt.
        definition = copy.deepcopy(competition["definition"])
        definition["variant"]["abschnitte"][0]["serien_gewertet"] = 3
        await _ok(
            client,
            "PATCH",
            f"/tournaments/{tid}/competitions/{competition['id']}",
            json={"definition": definition},
        )

    edit_yaml(catalog_copy / GROUP, _more_targets)

    async with start_app(catalog_copy) as client:
        cid = competition["id"]
        single = await _ok(client, "GET", f"/tournaments/{tid}/competitions/{cid}")
        listed = await _ok(client, "GET", f"/tournaments/{tid}/competitions")
        overview = await _ok(client, "GET", f"/tournaments/{tid}/overview")
        assert single["catalog_changed"] is True
        assert listed[0]["catalog_changed"] is True
        assert overview["competitions"][0]["catalog_changed"] is True
        assert single["catalog_stand_then"] == competition["catalog_stand_then"]

        # Kopie „wie letztes Jahr“: Der Vermerk reist mit, die Definition auch.
        copied = await _ok(
            client,
            "POST",
            f"/tournaments/{tid}/copy",
            201,
            json={"name": "VM", "date_from": "2027-05-01"},
        )
        copy_competition = copied["tournament"]["competitions"][0]
        assert copy_competition["catalog_changed"] is True
        assert copied["competitions"][0]["catalog_changed"] is True

        # Übernehmen setzt den Vermerk zurück.
        reset = await _ok(client, "POST", f"/tournaments/{tid}/competitions/{cid}/reset-definition")
        assert reset["catalog_changed"] is False
        assert reset["definition"]["variant"]["abschnitte"][0]["serien"] == 5
        again = await _ok(client, "GET", f"/tournaments/{tid}/competitions/{cid}")
        assert again["catalog_changed"] is False
        # Die Kopie behält ihren Vermerk, bis auch sie übernimmt.
        copy_now = await _ok(
            client,
            "GET",
            f"/tournaments/{copied['tournament']['id']}/competitions/{copy_competition['id']}",
        )
        assert copy_now["catalog_changed"] is True
