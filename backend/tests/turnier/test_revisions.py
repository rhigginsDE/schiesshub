"""Frei editierbarer Ablauf: Definition ändern, Revisionen, Grund im laufenden Turnier,
Vergleich mit dem Katalog, Startnummer."""

import copy
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InputError
from app.core.security import Actor
from app.modules.turnier import hooks
from app.modules.turnier.models import CompetitionRevision
from tests.turnier.conftest import API, Api

MEHRDISTANZ = "1201"  # Fertigkeit (4 Serien, Trefferaufnahme nach 2 und 4) + Parcours
SPEED = "1401"
FALLSCHEIBE = "4401"


async def competition_for(api: Api, code: str, **fields: Any) -> tuple[str, dict[str, Any]]:
    tournament = await api.create_tournament()
    tid = tournament["id"]
    competition = await api.create(
        tid, "competitions", catalog_federation="bds", catalog_code=code, **fields
    )
    api.drain()
    return f"{API}/tournaments/{tid}/competitions/{competition['id']}", competition


async def patch_definition(
    api: Api, url: str, change: Callable[[dict[str, Any]], None], **extra: Any
) -> dict[str, Any]:
    definition = (await api.client.get(url)).json()["definition"]
    change(definition)
    response = await api.client.patch(url, json={"definition": definition, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def section(definition: dict[str, Any], index: int = 0) -> dict[str, Any]:
    return definition["variant"]["abschnitte"][index]


async def diff_texts(api: Api, url: str) -> list[str]:
    response = await api.client.get(f"{url}/catalog-diff")
    assert response.status_code == 200, response.text
    return [entry["text"] for entry in response.json()["differences"]]


# --- Neue Felder über PATCH ----------------------------------------------------


async def test_counted_series_set_change_remove(api: Api) -> None:
    url, _ = await competition_for(api, MEHRDISTANZ)

    body = await patch_definition(api, url, lambda d: section(d).update(serien_gewertet=3))
    assert section(body["definition"])["serien_gewertet"] == 3
    assert await diff_texts(api, url) == ["Abschnitt Fertigkeit: 3 von 4 Serien gewertet"]

    body = await patch_definition(api, url, lambda d: section(d).update(serien_gewertet=2))
    assert section(body["definition"])["serien_gewertet"] == 2

    body = await patch_definition(api, url, lambda d: section(d).pop("serien_gewertet"))
    assert "serien_gewertet" not in section(body["definition"])
    assert await diff_texts(api, url) == []
    assert body["definition_revision"] == 4


async def test_hit_review_and_positions(api: Api) -> None:
    url, competition = await competition_for(api, MEHRDISTANZ)
    original = section(competition["definition"])

    def change(definition: dict[str, Any]) -> None:
        section(definition)["trefferaufnahme_nach"] = [4]
        section(definition)["positionen"][0]["anschlaege"] = [
            {"haltung": "stehend", "hand": "starke_hand"}
        ]

    body = await patch_definition(api, url, change)

    changed = section(body["definition"])
    assert changed["trefferaufnahme_nach"] == [4]
    assert changed["positionen"][0]["anschlaege"] == [{"haltung": "stehend", "hand": "starke_hand"}]
    assert changed["positionen"][1:] == original["positionen"][1:]
    assert await diff_texts(api, url) == [
        "Abschnitt Fertigkeit: Position in Serie 1 geändert",
        "Abschnitt Fertigkeit: Trefferaufnahme nur nach Serie 4 statt nach 2 und 4",
    ]

    body = await patch_definition(
        api, url, lambda d: [section(d).pop("trefferaufnahme_nach"), section(d).pop("positionen")]
    )
    assert {"trefferaufnahme_nach", "positionen"}.isdisjoint(section(body["definition"]))


async def test_speed_fields(api: Api) -> None:
    url, _ = await competition_for(api, SPEED)

    def change(definition: dict[str, Any]) -> None:
        section(definition)["ringwerte"] = [10, 8, 5, 0]
        definition["scoring"].pop("unbeendete_serie")

    body = await patch_definition(api, url, change)

    assert section(body["definition"])["ringwerte"] == [10, 8, 5, 0]
    assert "unbeendete_serie" not in body["definition"]["scoring"]
    assert await diff_texts(api, url) == [
        "Abschnitt Speed: Ringwerte 10, 8, 5, 0 statt 10, 7, 0",
        "Wertung: Nicht beendete Serie entfällt (Katalog: „ringe_bis_dahin_zeit_letzter_schuss“)",
    ]

    body = await patch_definition(
        api,
        url,
        lambda d: d["scoring"].update(unbeendete_serie="ringe_bis_dahin_zeit_letzter_schuss"),
    )
    assert body["definition"]["scoring"]["unbeendete_serie"] == (
        "ringe_bis_dahin_zeit_letzter_schuss"
    )


async def test_falling_plate_fields(api: Api) -> None:
    url, _ = await competition_for(api, FALLSCHEIBE)

    body = await patch_definition(
        api,
        url,
        lambda d: section(d).update(
            zeit_bei_abbruch_s=90, zuschlag_stoerung_vor_erstem_schuss_s=30
        ),
    )
    assert (
        section(body["definition"]).items()
        >= {
            "zeit_bei_abbruch_s": 90,
            "zuschlag_stoerung_vor_erstem_schuss_s": 30,
        }.items()
    )

    body = await patch_definition(api, url, lambda d: section(d).pop("zeit_bei_abbruch_s"))
    assert "zeit_bei_abbruch_s" not in section(body["definition"])
    assert section(body["definition"])["zuschlag_stoerung_vor_erstem_schuss_s"] == 30


@pytest.mark.parametrize(
    ("change", "field", "message"),
    [
        (
            {"serien_gewertet": 7},
            "definition.variant.abschnitte[0].serien_gewertet",
            "serien_gewertet ist 7, es gibt nur 4 Serien",
        ),
        (
            {"serien_gewertet": 0},
            "definition.variant.abschnitte[0].serien_gewertet",
            "muss größer als 0 sein",
        ),
        (
            {"trefferaufnahme_nach": [4, 2]},
            "definition.variant.abschnitte[0].trefferaufnahme_nach",
            "trefferaufnahme_nach muss aufsteigend sein, ohne Wiederholung",
        ),
        (
            {"trefferaufnahme_nach": [2, 9]},
            "definition.variant.abschnitte[0].trefferaufnahme_nach",
            "trefferaufnahme_nach nennt Serie 9, es gibt nur 4 Serien",
        ),
        (
            {"ringwerte": [7, 10]},
            "definition.variant.abschnitte[0].ringwerte",
            "ringwerte müssen absteigend sortiert sein und dürfen sich nicht wiederholen",
        ),
        (
            {"zeit_bei_abbruch_s": "lang"},
            "definition.variant.abschnitte[0].zeit_bei_abbruch_s",
            "muss eine Zahl sein",
        ),
        ({"kaliber": "9 mm"}, "definition.variant.abschnitte[0].kaliber", "unbekanntes Feld"),
    ],
)
async def test_definition_errors_are_german_and_precise(
    api: Api, change: dict[str, Any], field: str, message: str
) -> None:
    url, competition = await competition_for(api, MEHRDISTANZ)
    definition = copy.deepcopy(competition["definition"])
    section(definition).update(change)

    response = await api.client.patch(url, json={"definition": definition})

    assert response.status_code == 422
    body = response.json()
    assert body["errors"] == [{"field": field, "message": message}]
    assert field in body["detail"]
    assert (await api.client.get(url)).json() == competition


async def test_scoring_errors_are_precise(api: Api) -> None:
    url, competition = await competition_for(api, SPEED)
    definition = copy.deepcopy(competition["definition"])
    definition["scoring"]["unbeendete_serie"] = "abbrechen"

    response = await api.client.patch(url, json={"definition": definition})

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "definition.scoring.unbeendete_serie",
            "message": "muss einer dieser Werte sein: 'ringe_bis_dahin_zeit_letzter_schuss'",
        }
    ]


# --- Revisionen ------------------------------------------------------------------


async def test_revisions_record_every_scoring_change(api: Api) -> None:
    url, competition = await competition_for(api, MEHRDISTANZ)
    assert competition["definition_revision"] == 1

    await patch_definition(api, url, lambda d: section(d).update(serien_gewertet=3))
    await api.client.patch(url, json={"multi_start_rule": "all", "reason": "Vorstand"})
    # Name und Startgeld sind nicht wertungsrelevant.
    unchanged = await api.client.patch(url, json={"name": "Mehrdistanz", "fee_first_cents": 500})
    assert unchanged.json()["definition_revision"] == 3

    revisions = (await api.client.get(f"{url}/revisions")).json()

    assert [r["revision"] for r in revisions] == [1, 2, 3]
    assert revisions[0]["definition"] == competition["definition"]
    assert "serien_gewertet" in section(revisions[1]["definition"])
    assert [r["multi_start_rule"] for r in revisions] == ["best", "best", "all"]
    assert [r["reason"] for r in revisions] == [None, None, "Vorstand"]
    assert {r["competition_id"] for r in revisions} == {competition["id"]}
    single = await api.client.get(f"{url}/revisions/2")
    assert single.json() == revisions[1]
    missing = await api.client.get(f"{url}/revisions/9")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Die Revision 9 gibt es für diesen Wettbewerb nicht."}
    assert (await api.client.get(f"{url}/revisions/0")).status_code == 422
    events = [(e.name, e.data.get("revision")) for e in api.drain()]
    assert events == [
        ("competition.updated", None),
        ("competition.definition_changed", 2),
        ("competition.updated", None),
        ("competition.definition_changed", 3),
        ("competition.updated", None),
    ]


async def test_active_tournament_needs_a_reason(api: Api) -> None:
    url, competition = await competition_for(api, MEHRDISTANZ)
    tid = competition["tournament_id"]
    activated = await api.client.post(f"{API}/tournaments/{tid}/status", json={"status": "active"})
    assert activated.status_code == 200
    definition = copy.deepcopy(competition["definition"])
    section(definition)["serien_gewertet"] = 3

    without = await api.client.patch(url, json={"definition": definition})
    blank = await api.client.patch(url, json={"definition": definition, "reason": "  "})
    fee_only = await api.client.patch(url, json={"fee_first_cents": 800})

    assert without.status_code == blank.status_code == 422
    assert without.json() == {
        "detail": "Das Turnier läuft bereits. Für eine Änderung an der Wertung bitte einen "
        "Grund angeben.",
        "errors": [
            {
                "field": "reason",
                "message": "Das Turnier läuft bereits. Für eine Änderung an der Wertung bitte "
                "einen Grund angeben.",
            }
        ],
    }
    assert fee_only.status_code == 200
    assert fee_only.json()["definition_revision"] == 1
    api.drain()

    accepted = await api.client.patch(
        url, json={"definition": definition, "reason": "Nur 3 Serien wegen Zeitnot"}
    )

    assert accepted.status_code == 200
    assert accepted.json()["definition_revision"] == 2
    assert section(accepted.json()["definition"])["serien_gewertet"] == 3
    revision = (await api.client.get(f"{url}/revisions/2")).json()
    assert revision["reason"] == "Nur 3 Serien wegen Zeitnot"
    assert [(e.name, e.data) for e in api.drain()] == [
        ("competition.updated", {"tournament_id": tid, "competition_id": competition["id"]}),
        (
            "competition.definition_changed",
            {"tournament_id": tid, "competition_id": competition["id"], "revision": 2},
        ),
    ]
    audit = (await api.client.get(f"{API}/audit")).json()
    entries = [e for e in audit["items"] if e["action"] == "competition.definition_changed"]
    assert len(entries) == 1
    assert entries[0]["entity"] == "competition"
    assert entries[0]["entity_id"] == competition["id"]
    assert entries[0]["details"] == {
        "tournament_id": tid,
        "revision": 2,
        "fields": ["definition"],
        "reason": "Nur 3 Serien wegen Zeitnot",
        "tournament_status": "active",
    }

    reset = await api.client.post(f"{url}/reset-definition", json={})
    assert reset.status_code == 422
    assert reset.json()["errors"][0]["field"] == "reason"
    reset = await api.client.post(f"{url}/reset-definition", json={"reason": "Doch alle Serien"})
    assert reset.status_code == 200
    assert reset.json()["definition_revision"] == 3
    assert reset.json()["definition"] == competition["definition"]


async def test_closed_tournament_stays_locked(api: Api) -> None:
    url, competition = await competition_for(api, MEHRDISTANZ)
    tid = competition["tournament_id"]
    for target in ("active", "closed"):
        await api.client.post(f"{API}/tournaments/{tid}/status", json={"status": target})

    response = await api.client.patch(url, json={"capture_mode": "shot", "reason": "Korrektur"})

    assert response.status_code == 409


async def test_revisions_of_unknown_competition(api: Api) -> None:
    tournament = await api.create_tournament()
    url = f"{API}/tournaments/{tournament['id']}/competitions/{tournament['id']}"

    assert (await api.client.get(f"{url}/revisions")).status_code == 404
    assert (await api.client.get(f"{url}/catalog-diff")).status_code == 404


# --- Vergleich mit dem Katalog -------------------------------------------------


async def test_catalog_diff_shape(api: Api) -> None:
    url, _ = await competition_for(api, MEHRDISTANZ)
    await patch_definition(api, url, lambda d: section(d, 1).update(sollzeit_s=90))

    response = await api.client.get(f"{url}/catalog-diff")

    assert response.json() == {
        "deviates": True,
        "federation": "bds",
        "code": MEHRDISTANZ,
        "variant_id": "variante-1",
        "catalog_stand": "2026-06-30",
        "catalog_available": True,
        "differences": [
            {
                "path": "variant.abschnitte[1].sollzeit_s",
                "catalog_value": 80,
                "tournament_value": 90,
                "text": "Abschnitt Parcours: Sollzeit 90 s statt 80 s",
                "section_id": "parcours",
            }
        ],
    }


async def test_catalog_diff_follows_the_source_variant(api: Api) -> None:
    url, _ = await competition_for(api, MEHRDISTANZ, variant_id="variante-2-pistole")

    response = (await api.client.get(f"{url}/catalog-diff")).json()

    assert response["variant_id"] == "variante-2-pistole"
    assert response["deviates"] is False


async def test_catalog_diff_without_catalog_origin(api: Api) -> None:
    tournament = await api.create_tournament()
    definition = {
        "variant": {
            "id": "eigen",
            "name": "Eigen",
            "abschnitte": [{"id": "a", "name": "A", "serien": 2, "serien_gewertet": 1}],
        },
        "scoring": {"modell": "ringe", "rangfolge": "absteigend", "geprueft": False},
    }
    own = await api.create(tournament["id"], "competitions", name="Eigen", definition=definition)

    response = await api.client.get(
        f"{API}/tournaments/{tournament['id']}/competitions/{own['id']}/catalog-diff"
    )

    assert response.json() == {
        "deviates": False,
        "federation": None,
        "code": None,
        "variant_id": None,
        "catalog_stand": None,
        "catalog_available": False,
        "differences": [],
    }


# --- Startnummer ---------------------------------------------------------------


async def test_first_start_number_setting(api: Api) -> None:
    tournament = await api.create_tournament(settings={"first_start_number": 100})
    url = f"{API}/tournaments/{tournament['id']}"

    assert tournament["settings"]["first_start_number"] == 100
    changed = await api.client.patch(url, json={"settings": {"first_start_number": 501}})
    assert changed.json()["settings"]["first_start_number"] == 501
    refused = await api.client.patch(url, json={"settings": {"first_start_number": 0}})
    assert refused.status_code == 422
    assert refused.json()["errors"] == [
        {"field": "settings.first_start_number", "message": "muss mindestens 1 sein"}
    ]


# --- Serverinterne Callbacks -----------------------------------------------------


async def test_definition_changed_callbacks_run_in_the_same_transaction(api: Api) -> None:
    url, competition = await competition_for(api, MEHRDISTANZ)
    calls: list[tuple[str, int, int]] = []

    async def recompute(
        session: AsyncSession, competition_id: uuid.UUID, revision: int, actor: Actor
    ) -> None:
        # Die neue Revision ist in dieser Transaktion schon sichtbar.
        stored = await session.scalar(
            select(func.count()).where(CompetitionRevision.competition_id == competition_id)
        )
        calls.append((str(competition_id), revision, stored or 0))
        if revision == 3:
            raise InputError.single(None, "Neuberechnung fehlgeschlagen.")

    hooks.register_definition_changed(recompute)
    try:
        await patch_definition(api, url, lambda d: section(d).update(serien_gewertet=3))
        await api.client.patch(url, json={"name": "Nur der Name"})
        refused = await api.client.patch(url, json={"capture_mode": "shot"})
    finally:
        hooks.unregister_definition_changed(recompute)

    assert calls == [(competition["id"], 2, 2), (competition["id"], 3, 3)]
    # Wirft ein Callback, ist die ganze Änderung verworfen.
    assert refused.status_code == 422
    current = (await api.client.get(url)).json()
    assert (current["capture_mode"], current["definition_revision"]) == ("series", 2)
    assert len((await api.client.get(f"{url}/revisions")).json()) == 2
