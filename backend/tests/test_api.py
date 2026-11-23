"""API-Tests gegen die echte PostgreSQL-Testdatenbank und den echten Katalog."""

import tomllib
from collections.abc import Callable
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.core.config import Settings
from app.main import create_app
from tests.conftest import BACKEND_DIR, REAL_CATALOG_DIR, ClientFactory, edit_yaml, running

API = "/api/v1"


async def row_counts(engine: AsyncEngine) -> dict[str, int]:
    """Zeilen je Tabelle, aktive wie inaktive."""
    tables = ["catalog_federation", "catalog_group", "catalog_discipline", "catalog_class"]
    async with engine.connect() as connection:
        return {
            table: (await connection.scalar(text(f"SELECT count(*) FROM {table}"))) or 0
            for table in tables
        }


# --- Health ------------------------------------------------------------------


async def test_health(client: httpx.AsyncClient, real_catalog_counts: dict[str, int]) -> None:
    response = await client.get(f"{API}/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "version", "db", "katalog"}
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["db"] == "ok"
    katalog = body["katalog"]
    assert set(katalog) == {
        "verbaende",
        "gruppen",
        "disziplinen",
        "klassen",
        "importiert_am",
        "fehler",
    }
    assert katalog["verbaende"] == 1
    assert katalog["gruppen"] == real_catalog_counts["gruppen"]
    assert katalog["disziplinen"] == real_catalog_counts["disziplinen"]
    assert katalog["klassen"] == real_catalog_counts["klassen"]
    assert katalog["importiert_am"] is not None
    assert katalog["fehler"] == []


def test_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == __version__


async def test_openapi_and_docs_live_under_api_prefix(client: httpx.AsyncClient) -> None:
    openapi = await client.get(f"{API}/openapi.json")
    docs = await client.get(f"{API}/docs")

    assert openapi.status_code == 200
    assert docs.status_code == 200
    paths = set(openapi.json()["paths"])
    # Teilmenge statt Gleichheit: Jedes weitere Modul bringt eigene Pfade mit.
    assert paths >= {
        f"{API}/health",
        f"{API}/events",
        f"{API}/katalog/verbaende",
        f"{API}/katalog/gruppen",
        f"{API}/katalog/disziplinen",
        f"{API}/katalog/disziplinen/{{verband}}/{{kennziffer}}",
        f"{API}/katalog/klassen",
    }
    assert all(path.startswith(f"{API}/") for path in paths)
    assert (await client.get("/openapi.json")).status_code == 404
    assert (await client.get("/docs")).status_code == 404


async def test_docs_are_marked_as_development_only(client: httpx.AsyncClient) -> None:
    page = (await client.get(f"{API}/docs")).text

    assert "nur Entwicklung" in page
    assert "Nur Entwicklung" in page
    assert f"{API}/openapi.json" in page


async def test_docs_are_off_outside_development(
    clean_db: None, settings_for: Callable[[Path], Settings]
) -> None:
    settings = settings_for(REAL_CATALOG_DIR).model_copy(update={"environment": "production"})
    async with running(create_app(settings)) as client:
        docs = await client.get(f"{API}/docs")
        openapi = await client.get(f"{API}/openapi.json")

    assert docs.status_code == 404
    # Die Beschreibung braucht kein Internet und bleibt für den Client-Generator erreichbar.
    assert openapi.status_code == 200


async def test_validation_errors_are_german(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{API}/tournaments/kein-schluessel")
    schema = (await client.get(f"{API}/openapi.json")).json()["components"]["schemas"]

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Feld ‚tournament_id‘: muss eine gültige ID (UUID) sein.",
        "errors": [{"field": "tournament_id", "message": "muss eine gültige ID (UUID) sein"}],
    }
    assert set(schema["HTTPValidationError"]["required"]) == {"detail", "errors"}


async def test_modules_stop_their_background_work_on_shutdown(
    clean_db: None, settings_for: Callable[[Path], Settings]
) -> None:
    app = create_app(settings_for(REAL_CATALOG_DIR))
    async with running(app):
        task = app.state.backup._task
        assert task is not None
        assert not task.done()

    assert task.done()


async def test_cors_allows_the_vite_dev_server_only(client: httpx.AsyncClient) -> None:
    allowed = await client.get(f"{API}/health", headers={"Origin": "http://localhost:5180"})
    other = await client.get(f"{API}/health", headers={"Origin": "http://boese.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5180"
    assert "access-control-allow-origin" not in other.headers


# --- Katalog -----------------------------------------------------------------


async def test_federations(client: httpx.AsyncClient, real_catalog_counts: dict[str, int]) -> None:
    response = await client.get(f"{API}/katalog/verbaende")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "bds",
            "kuerzel": "BDS",
            "name": "Bund Deutscher Sportschützen 1975 e.V.",
            "regelwerk": {
                "name": "BDS-Sporthandbuch, Teil K (Kurzwaffen) und Teil L (Langwaffen)",
                "stand": "2026-06-30",
            },
            "status": "entwurf",
            "anzahl_gruppen": real_catalog_counts["gruppen"],
            "anzahl_disziplinen": real_catalog_counts["disziplinen"],
        }
    ]


async def test_groups(client: httpx.AsyncClient, real_catalog_counts: dict[str, int]) -> None:
    response = await client.get(f"{API}/katalog/gruppen", params={"verband": "bds"})

    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == real_catalog_counts["gruppen"]
    assert sum(group["anzahl"] for group in groups) == real_catalog_counts["disziplinen"]
    by_id = {group["id"]: group for group in groups}
    assert by_id["flinte-15m-fallscheibe"] == {
        "verband": "bds",
        "id": "flinte-15m-fallscheibe",
        "name": "Flinte 15 m Fallscheibe",
        "waffenart": "flinte",
        "distanz_m": 15,
        "art": "fallscheibe",
        "anzahl": 6,
        "wertung_modell": "zeit_plus_zuschlaege",
        "geprueft": True,
    }
    assert by_id["kw-mehrdistanz"]["distanz_m"] is None


async def test_disciplines_of_a_group(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"{API}/katalog/disziplinen", params={"verband": "bds", "gruppe": "flinte-15m-fallscheibe"}
    )

    assert response.status_code == 200
    disciplines = response.json()
    assert [d["kennziffer"] for d in disciplines] == [
        "4401",
        "4402",
        "4403",
        "4404",
        "4405",
        "4406",
    ]
    assert disciplines[1] == {
        "verband": "bds",
        "kennziffer": "4402",
        "name": "Selbstladeflinte, optische Visierung",
        "gruppe_id": "flinte-15m-fallscheibe",
        "gruppe_name": "Flinte 15 m Fallscheibe",
        "waffe": "Flinte, Selbstlader",
        "munition": "Schrot bis 12/89; max. 3,0 mm, Vorlage 24–32 g, kein Stahlschrot",
        "visierung": "beliebige Optik",
        "anschlag": "stehend freihändig, Voranschlag",
        "scheibe": "Z12",
        "optional": False,
        "hinweis": "Wechselmagazine erlaubt",
    }
    assert disciplines[0]["hinweis"] is None


async def test_all_disciplines(
    client: httpx.AsyncClient, real_catalog_counts: dict[str, int]
) -> None:
    response = await client.get(f"{API}/katalog/disziplinen", params={"verband": "bds"})

    disciplines = response.json()
    assert len(disciplines) == real_catalog_counts["disziplinen"]
    codes = [d["kennziffer"] for d in disciplines]
    assert codes == sorted(codes)
    assert len(set(codes)) == len(codes)


async def test_discipline_search_by_code_and_name(client: httpx.AsyncClient) -> None:
    by_code = (await client.get(f"{API}/katalog/disziplinen", params={"q": "440"})).json()
    by_name = (
        await client.get(
            f"{API}/katalog/disziplinen", params={"verband": "bds", "q": "repetierFLINTE"}
        )
    ).json()
    nothing = (await client.get(f"{API}/katalog/disziplinen", params={"q": "%"})).json()

    assert {d["kennziffer"] for d in by_code} >= {"4401", "4406"}
    assert all("440" in d["kennziffer"] or "440" in d["name"] for d in by_code)
    assert by_name
    assert all("repetierflinte" in d["name"].lower() for d in by_name)
    assert all("%" in d["name"] for d in nothing)


async def test_discipline_detail(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{API}/katalog/disziplinen/bds/4402")

    assert response.status_code == 200
    body = response.json()
    assert body["kennziffer"] == "4402"
    assert body["gruppe_id"] == "flinte-15m-fallscheibe"
    assert body["pruefen"] == []
    assert body["fruehere_kennziffer"] is None
    assert body["ablauf"] == {
        "schluessel": "fallscheibe-max6",
        "beschreibung": (
            "4 Serien auf je 5 Fallscheiben; max. 6 Schuss und 1 Min. je Serie; "
            "10 s Zuschlag je stehender Scheibe"
        ),
        "varianten": [
            {
                "id": "standard",
                "name": "Standard",
                "abschnitte": [
                    {
                        "id": "fallscheibe",
                        "name": "Fallscheibe",
                        "serien": 4,
                        "ziele_je_serie": 5,
                        "max_schuss_je_serie": 6,
                        "max_zeit_je_serie_s": 60,
                        "zeit_wird_gemessen": True,
                        "zuschlag_je_stehender_scheibe_s": 10,
                        "zeit_bei_abbruch_s": 60,
                        "zuschlag_stoerung_vor_erstem_schuss_s": 50,
                    }
                ],
            }
        ],
    }
    assert body["wertung"] == {
        "modell": "zeit_plus_zuschlaege",
        "rangfolge": "aufsteigend",
        "geprueft": True,
    }


async def test_discipline_detail_multi_distance(client: httpx.AsyncClient) -> None:
    body = (await client.get(f"{API}/katalog/disziplinen/bds/1201")).json()

    # 1201 ist eine Pistole: keine Revolver-Variante
    assert [v["id"] for v in body["ablauf"]["varianten"]] == ["variante-1", "variante-2-pistole"]
    parcours = body["ablauf"]["varianten"][0]["abschnitte"][1]
    assert parcours["distanzen_m"] == [20, 15, 10, 5]
    assert parcours["sollzeit_s"] == 80
    assert [p["nr"] for p in parcours["positionen"]] == [5, 6, 7, 8]
    assert parcours["positionen"][1]["anschlaege"] == [
        {"haltung": "kniend", "hand": "beidhaendig"},
        {"haltung": "stehend", "hand": "schwache_hand"},
    ]
    assert parcours["positionen"][3]["scheibe"] == 4
    assert body["wertung"]["modell"] == "ringe_mit_zeitabzug"
    assert body["wertung"]["gleichstand"] == ["zehner", "innenzehner", "neuner_abwaerts"]


async def test_unknown_discipline_gives_german_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{API}/katalog/disziplinen/bds/9999")

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "Die Disziplin mit der Kennziffer „9999“ gibt es im Katalog des Verbands „bds“ nicht."
        )
    }


async def test_unknown_federation_gives_german_404(client: httpx.AsyncClient) -> None:
    expected = {"detail": "Der Verband „dsb“ ist im Katalog nicht vorhanden."}

    for path in (
        "/katalog/disziplinen/dsb/1001",
        "/katalog/gruppen?verband=dsb",
        "/katalog/disziplinen?verband=dsb",
        "/katalog/klassen?verband=dsb",
    ):
        response = await client.get(f"{API}{path}")
        assert response.status_code == 404, path
        assert response.json() == expected, path


async def test_classes(client: httpx.AsyncClient, real_catalog_counts: dict[str, int]) -> None:
    response = await client.get(f"{API}/katalog/klassen", params={"verband": "bds"})

    assert response.status_code == 200
    classes = response.json()
    assert len(classes) == real_catalog_counts["klassen"]
    # Reihenfolge wie in der Datei.
    assert classes[0]["id"] == "jugend-1"
    senioren = next(klasse for klasse in classes if klasse["id"] == "senioren")
    assert senioren == {
        "verband": "bds",
        "id": "senioren",
        "name": "Seniorenklasse",
        "kurz": "Sen",
        "geschlecht": "maennlich",
        "alter_hilfe": "mind. 60 zu Beginn des Sportjahres, bis zum Sportjahr, in dem er 70 wird",
        "mindeststarter_dm": 5,
        "zusammenlegen_in": ["alters", "schuetzen"],
        "zusammenlegen_nach_alter": False,
        "hinweis": None,
        "nummer": None,
        "satz": None,
        "hoeher_in": [],
    }


# --- Import ------------------------------------------------------------------


async def test_second_start_creates_no_duplicates(
    start_app: ClientFactory, engine: AsyncEngine, real_catalog_counts: dict[str, int]
) -> None:
    async with start_app(REAL_CATALOG_DIR):
        first = await row_counts(engine)
    async with start_app(REAL_CATALOG_DIR) as client:
        second = await row_counts(engine)
        health = (await client.get(f"{API}/health")).json()

    assert first == second
    assert first == {
        "catalog_federation": 1,
        "catalog_group": real_catalog_counts["gruppen"],
        "catalog_discipline": real_catalog_counts["disziplinen"],
        "catalog_class": real_catalog_counts["klassen"],
    }
    assert health["katalog"]["disziplinen"] == real_catalog_counts["disziplinen"]


async def test_removed_entries_become_inactive_and_can_return(
    start_app: ClientFactory, engine: AsyncEngine, catalog_copy: Path
) -> None:
    group_file = catalog_copy / "bds" / "gruppen" / "flinte-15m-fallscheibe.yaml"
    original = group_file.read_text(encoding="utf-8")
    async with start_app(catalog_copy):
        before = await row_counts(engine)

    # Eine Disziplin geändert, eine entfernt.
    def change(data: dict) -> None:
        data["disziplinen"][0]["name"] = "Neuer Name"
        del data["disziplinen"][5]

    edit_yaml(group_file, change)
    async with start_app(catalog_copy) as client:
        listed = (
            await client.get(
                f"{API}/katalog/disziplinen", params={"gruppe": "flinte-15m-fallscheibe"}
            )
        ).json()
        removed = await client.get(f"{API}/katalog/disziplinen/bds/4406")
        health = (await client.get(f"{API}/health")).json()

    assert [d["kennziffer"] for d in listed] == ["4401", "4402", "4403", "4404", "4405"]
    assert listed[0]["name"] == "Neuer Name"
    assert removed.status_code == 404
    assert health["katalog"]["disziplinen"] == before["catalog_discipline"] - 1
    # Nichts wurde gelöscht.
    assert await row_counts(engine) == before
    async with engine.connect() as connection:
        active = await connection.scalar(
            text("SELECT active FROM catalog_discipline WHERE code = '4406'")
        )
    assert active is False

    # Eine ganze Gruppe verschwindet: Gruppe und ihre Disziplinen werden inaktiv.
    group_file.unlink()
    async with start_app(catalog_copy) as client:
        groups = (await client.get(f"{API}/katalog/gruppen")).json()
        health = (await client.get(f"{API}/health")).json()
    assert "flinte-15m-fallscheibe" not in {group["id"] for group in groups}
    assert health["katalog"]["gruppen"] == before["catalog_group"] - 1
    assert health["katalog"]["disziplinen"] == before["catalog_discipline"] - 6
    assert await row_counts(engine) == before

    # Kommt die Datei zurück, werden dieselben Zeilen wieder aktiv.
    group_file.write_text(original, encoding="utf-8")
    async with start_app(catalog_copy) as client:
        health = (await client.get(f"{API}/health")).json()
    assert health["katalog"]["disziplinen"] == before["catalog_discipline"]
    assert await row_counts(engine) == before


async def test_broken_catalog_keeps_old_state_and_shows_in_health(
    start_app: ClientFactory, catalog_copy: Path, real_catalog_counts: dict[str, int]
) -> None:
    async with start_app(catalog_copy) as client:
        imported_at = (await client.get(f"{API}/health")).json()["katalog"]["importiert_am"]

    group_file = catalog_copy / "bds" / "gruppen" / "flinte-15m-fallscheibe.yaml"

    def change(data: dict) -> None:
        data["disziplinen"][0]["name"] = "Darf nicht ankommen"
        data["disziplinen"][2]["kaliber"] = "12/70"

    edit_yaml(group_file, change)

    # Der Server startet trotzdem.
    async with start_app(catalog_copy) as client:
        response = await client.get(f"{API}/health")
        detail = (await client.get(f"{API}/katalog/disziplinen/bds/4401")).json()

    assert response.status_code == 200
    health = response.json()
    assert health["status"] == "eingeschraenkt"
    assert health["db"] == "ok"
    assert health["katalog"]["fehler"] == [
        {
            "verband": "bds",
            "datei": "bds/gruppen/flinte-15m-fallscheibe.yaml",
            "pfad": "disziplinen[2].kaliber",
            "meldung": "unbekanntes Feld",
        }
    ]
    assert health["katalog"]["disziplinen"] == real_catalog_counts["disziplinen"]
    assert health["katalog"]["importiert_am"] == imported_at
    assert detail["name"] == "Selbstladeflinte, offene Visierung"


async def test_missing_catalog_directory_does_not_stop_the_server(
    start_app: ClientFactory, tmp_path: Path
) -> None:
    async with start_app(tmp_path / "fehlt") as client:
        response = await client.get(f"{API}/health")

    assert response.status_code == 200
    health = response.json()
    assert health["status"] == "eingeschraenkt"
    assert health["katalog"]["verbaende"] == 0
    assert health["katalog"]["importiert_am"] is None
    assert len(health["katalog"]["fehler"]) == 1


async def test_removed_federation_becomes_inactive(
    start_app: ClientFactory, engine: AsyncEngine, minimal_catalog: Path, tmp_path: Path
) -> None:
    async with start_app(minimal_catalog) as client:
        assert [v["id"] for v in (await client.get(f"{API}/katalog/verbaende")).json()] == ["tst"]

    empty = tmp_path / "leer"
    empty.mkdir()
    async with start_app(empty) as client:
        federations = (await client.get(f"{API}/katalog/verbaende")).json()
        health = (await client.get(f"{API}/health")).json()

    assert federations == []
    assert health["katalog"] | {"importiert_am": None} == {
        "verbaende": 0,
        "gruppen": 0,
        "disziplinen": 0,
        "klassen": 0,
        "importiert_am": None,
        "fehler": [],
    }
    assert (await row_counts(engine))["catalog_discipline"] == 2
