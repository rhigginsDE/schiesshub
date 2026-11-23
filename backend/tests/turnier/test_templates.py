"""Fertige Vorlagen: Dateien, Auflösung gegen den echten Katalog, Anlegen aus einer Vorlage."""

from pathlib import Path

import pytest
import yaml

from app.modules.turnier import tournament_templates
from app.modules.turnier.tournament_templates import (
    TEMPLATE_DIR,
    TemplateCompetition,
    TemplateFileError,
    TournamentTemplate,
    load_templates,
)
from tests.conftest import REAL_CATALOG_DIR
from tests.turnier.conftest import API, Api

REQUIRED = {
    "vereinsmeisterschaft-kurzwaffe": "Vereinsmeisterschaft Kurzwaffe",
    "fallscheibe-flinte-15m": "Fallscheibe Flinte 15 m",
    "offenes-turnier": "Offenes Turnier",
}


def _real_codes() -> set[tuple[str, str]]:
    """Kennziffern direkt aus den Katalogdateien, unabhängig vom Code unter Test."""
    codes = set()
    for federation in REAL_CATALOG_DIR.iterdir():
        for path in (federation / "gruppen").glob("*.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            codes |= {(federation.name, item["kennziffer"]) for item in data["disziplinen"]}
    return codes


def test_template_files_load_and_contain_the_required_templates() -> None:
    templates = load_templates()

    assert {key: templates[key].name for key in REQUIRED} == REQUIRED
    assert sorted(templates) == sorted(path.stem for path in TEMPLATE_DIR.glob("*.yaml"))
    for template in templates.values():
        # Ein Satz Beschreibung.
        assert template.description.endswith(".")
        assert template.description.count(". ") == 0


def test_every_template_code_exists_in_the_real_catalog_files() -> None:
    codes = _real_codes()
    for template in load_templates().values():
        for item in template.competitions:
            assert (item.catalog_federation, item.catalog_code) in codes, (
                template.id,
                item.catalog_code,
            )


def test_fallscheibe_template_is_the_first_club_goal() -> None:
    template = load_templates()["fallscheibe-flinte-15m"]
    codes = [item.catalog_code for item in template.competitions]

    # Erstes Ziel des Vereins (Entscheidungen.md): Flinte 15 m Fallscheibe, Kennziffern 4401–4406.
    assert codes == ["4401", "4402", "4403", "4404", "4405", "4406"]


def test_templates_carry_no_rules() -> None:
    """Vorlagen verweisen nur auf den Katalog; Regelfelder sind dort gar nicht erlaubt."""
    rule_fields = {"definition", "variant", "scoring", "abschnitte", "wertung", "ablauf"}
    assert not rule_fields & set(TemplateCompetition.model_fields)
    assert not rule_fields & set(TournamentTemplate.model_fields)
    for path in TEMPLATE_DIR.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert "abschnitte" not in text
        assert "wertung" not in text


def test_invalid_template_file_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "kaputt.yaml").write_text(
        'schema: 1\nid: "anders"\nname: "X"\ndescription: "Y."\n'
        'competitions: [{catalog_federation: "bds", catalog_code: "1001"}]\n',
        encoding="utf-8",
    )
    with pytest.raises(TemplateFileError, match=r"kaputt\.yaml: Die id „anders“"):
        load_templates.__wrapped__(tmp_path)

    (tmp_path / "kaputt.yaml").write_text(
        'schema: 1\nid: "kaputt"\nname: "X"\ndescription: "Y."\n'
        'competitions: [{catalog_federation: "bds", catalog_code: "1001", range: "fehlt"}]\n',
        encoding="utf-8",
    )
    with pytest.raises(TemplateFileError, match="Schießstand „fehlt“"):
        load_templates.__wrapped__(tmp_path)


async def test_list_resolves_every_template_against_the_real_catalog(api: Api) -> None:
    response = await api.client.get(f"{API}/tournament-templates")

    assert response.status_code == 200
    listed = {item["id"]: item for item in response.json()}
    assert set(REQUIRED) <= set(listed)
    for item in listed.values():
        assert item["competitions"], item["id"]
        for competition in item["competitions"]:
            assert competition["available"] is True, (item["id"], competition)
            assert competition["name"]
    fallscheibe = listed["fallscheibe-flinte-15m"]
    assert fallscheibe["template"] == "custom"
    assert fallscheibe["classes_federation"] == "bds"
    assert fallscheibe["ranges"] == [{"name": "Schießstand Flinte 15 m", "lane_count": 2}]
    assert fallscheibe["competitions"][0] == {
        "catalog_federation": "bds",
        "catalog_code": "4401",
        "name": "Selbstladeflinte, offene Visierung",
        "available": True,
    }


@pytest.mark.parametrize("template_id", sorted(load_templates()))
async def test_every_template_can_be_created_from_the_real_catalog(
    api: Api, template_id: str
) -> None:
    template = load_templates()[template_id]
    response = await api.client.post(
        f"{API}/tournaments/from-template",
        json={"template_id": template_id, "name": "Aus Vorlage", "date_from": "2027-05-01"},
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["status"] == "draft"
    assert created["is_practice"] is False
    assert created["template"] == template.template
    assert [c["catalog_code"] for c in created["competitions"]] == [
        item.catalog_code for item in template.competitions
    ]
    assert [r["name"] for r in created["ranges"]] == [item.name for item in template.ranges]
    assert len(created["classes"]) > 0
    for competition in created["competitions"]:
        # Frisch aus dem Katalog: keine Abweichung.
        diff = await api.client.get(
            f"{API}/tournaments/{created['id']}/competitions/{competition['id']}/catalog-diff"
        )
        assert diff.json()["deviates"] is False
        assert diff.json()["catalog_available"] is True
        assert competition["range_id"] in {r["id"] for r in created["ranges"]}


async def test_club_championship_template_uses_its_settings(api: Api) -> None:
    response = await api.client.post(
        f"{API}/tournaments/from-template",
        json={
            "template_id": "vereinsmeisterschaft-kurzwaffe",
            "name": "VM 2027",
            "date_from": "2027-05-01",
            "date_to": "2027-05-02",
            "organizer": "SV Musterstadt",
        },
    )

    created = response.json()
    assert created["organizer"] == "SV Musterstadt"
    assert created["date_to"] == "2027-05-02"
    assert created["settings"]["default_multi_start"] is False
    assert all(c["multi_start"] is False for c in created["competitions"])
    # Präzision hat feste Serienzeiten: Zeitplan.
    assert {c["planning"] for c in created["competitions"]} == {"schedule"}
    announcement = await api.client.get(f"{API}/tournaments/{created['id']}/announcement")
    headings = {b["id"]: b["heading"] for b in announcement.json()["blocks"]}
    assert headings["wettbewerbe"] == "Disziplinen der Vereinsmeisterschaft"


async def test_fallscheibe_template_plans_by_queue(api: Api) -> None:
    response = await api.client.post(
        f"{API}/tournaments/from-template",
        json={
            "template_id": "fallscheibe-flinte-15m",
            "name": "Fallscheibe",
            "date_from": "2027-05-01",
        },
    )

    assert {c["planning"] for c in response.json()["competitions"]} == {"queue"}


async def test_unknown_template_is_an_input_error(api: Api) -> None:
    response = await api.client.post(
        f"{API}/tournaments/from-template",
        json={"template_id": "gibt-es-nicht", "name": "X", "date_from": "2027-05-01"},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "template_id"
    assert "„offenes-turnier“" in response.json()["detail"]


async def test_template_with_unknown_code_creates_nothing(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = TournamentTemplate.model_validate(
        {
            "schema": 1,
            "id": "kaputt",
            "name": "Kaputt",
            "description": "Verweist auf eine erfundene Kennziffer.",
            "competitions": [
                {"catalog_federation": "bds", "catalog_code": "1001"},
                {"catalog_federation": "bds", "catalog_code": "9999"},
            ],
        }
    )
    monkeypatch.setattr(tournament_templates, "load_templates", lambda: {"kaputt": broken})

    listed = await api.client.get(f"{API}/tournament-templates")
    response = await api.client.post(
        f"{API}/tournaments/from-template",
        json={"template_id": "kaputt", "name": "X", "date_from": "2027-05-01"},
    )

    assert [c["available"] for c in listed.json()[0]["competitions"]] == [True, False]
    assert response.status_code == 409
    assert "bds 9999" in response.json()["detail"]
    assert (await api.client.get(f"{API}/tournaments")).json() == []
