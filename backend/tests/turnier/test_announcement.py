"""Turnierausschreibung: Standardgliederung, Prüfung, Reihenfolge/Sichtbarkeit, Druckfassung."""

import copy
from typing import Any

import pytest

from app.core import begriffe
from app.core.begriffe import begriffe_fuer
from app.modules.turnier.announcement import document_terms, lanes_text
from app.modules.turnier.announcement_outline import DEFAULT_OUTLINE
from app.modules.turnier.models import Competition
from tests.turnier.conftest import API, Api


async def tournament(api: Api, **fields: Any) -> tuple[str, str]:
    created = await api.create_tournament(**fields)
    api.drain()
    return created["id"], f"{API}/tournaments/{created['id']}/announcement"


async def test_default_outline_has_headings_only(api: Api) -> None:
    _, url = await tournament(api)

    body = (await api.client.get(url)).json()

    assert body["title"] is None
    assert body["facts"] == {
        "venue": None,
        "address": None,
        "registration_deadline": None,
        "registration_info": None,
        "contact_name": None,
        "contact_info": None,
    }
    assert [(b["id"], b["kind"], b["heading"]) for b in body["blocks"]] == list(DEFAULT_OUTLINE)
    assert [b["heading"] for b in body["blocks"]] == [
        "Begrüßung",
        "Veranstalter und Ort",
        "Termine",
        "Teilnahmeberechtigung",
        "Wettbewerbe",
        "Schießstände",
        "Klassen",
        "Startgeld",
        "Anmeldung",
        "Ablauf",
        "Sicherheit und Waffenkontrolle",
        "Wertung und Siegerehrung",
        "Einsprüche",
        "Datenschutz",
        "Kontakt",
    ]
    assert all(b["body"] == "" and b["visible"] for b in body["blocks"])
    # Neue Turniere haben die ganze Standardgliederung.
    assert body["missing_default_blocks"] == []


async def test_club_championship_outline(api: Api) -> None:
    _, url = await tournament(api, template="club_championship")

    headings = {b["id"]: b["heading"] for b in (await api.client.get(url)).json()["blocks"]}

    assert headings["teilnahmeberechtigung"] == "Teilnahmeberechtigung"
    assert headings["wettbewerbe"] == "Disziplinen der Vereinsmeisterschaft"


async def test_put_reorders_hides_and_adds_text(api: Api) -> None:
    tid, url = await tournament(api)
    announcement = (await api.client.get(url)).json()
    blocks = announcement["blocks"]
    blocks.reverse()
    blocks[0]["visible"] = False
    blocks.append(
        {
            "id": "anfahrt",
            "kind": "text",
            "heading": "Anfahrt",
            "body": "Zeile 1\nZeile 2\n\nAbsatz",
            "visible": True,
        }
    )
    announcement["title"] = "Einladung zum Frühjahrspokal"
    announcement["facts"]["registration_deadline"] = "2027-02-28"
    announcement["facts"]["venue"] = "Schützenhaus"

    response = await api.client.put(url, json=announcement)

    assert response.status_code == 200, response.text
    assert (await api.client.get(url)).json() == response.json() == announcement
    assert [(e.name, e.data) for e in api.drain()] == [
        ("tournament.announcement_changed", {"tournament_id": tid})
    ]

    # Text-Bausteine lassen sich löschen; automatische auch (dann fehlen sie im Dokument).
    announcement["blocks"] = [b for b in blocks if b["id"] not in {"anfahrt", "klassen"}]
    assert (await api.client.put(url, json=announcement)).status_code == 200
    ids = [b["id"] for b in (await api.client.get(url)).json()["blocks"]]
    assert "anfahrt" not in ids
    assert "klassen" not in ids


def block(**fields: Any) -> dict[str, Any]:
    return {"id": "frei", "kind": "text", "heading": "Frei", "body": "", **fields}


@pytest.mark.parametrize(
    ("blocks", "field", "fragment"),
    [
        ([block(body="<b>fett</b>")], "blocks[0]", "kein HTML"),
        ([block(body="x" * 10001)], "blocks[0].body", "höchstens 10000 Zeichen"),
        ([block(kind="tabelle")], "blocks[0].kind", "muss einer dieser Werte sein"),
        ([block(farbe="rot")], "blocks[0].farbe", "unbekanntes Feld"),
        ([block(), block()], None, "Baustein-ID mehrfach vergeben: frei"),
        (
            [block(id="a", kind="fees"), block(id="b", kind="fees")],
            None,
            "nur einmal vorkommen: fees",
        ),
        ([block(id="Gross Klein")], "blocks[0].id", "nicht das erwartete Format"),
    ],
)
async def test_invalid_blocks(
    api: Api, blocks: list[dict[str, Any]], field: str | None, fragment: str
) -> None:
    _, url = await tournament(api)

    response = await api.client.put(url, json={"blocks": blocks})

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert len(errors) == 1
    assert errors[0]["field"] == field
    assert fragment in errors[0]["message"]


async def test_invalid_facts(api: Api) -> None:
    _, url = await tournament(api)

    response = await api.client.put(
        url, json={"facts": {"registration_deadline": "bald", "telefon": "1"}}
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "facts.registration_deadline",
            "message": "muss ein Datum im Format JJJJ-MM-TT sein",
        },
        {"field": "facts.telefon", "message": "unbekanntes Feld"},
    ]


async def test_document_contains_current_data(api: Api) -> None:
    tid, url = await tournament(api, settings={"currency": "CHF", "default_multi_start": True})
    range_ = await api.create(tid, "ranges", name="Schießstand 25 m", lane_count=6)
    await api.create(tid, "classes", code="offen", name="Offene Klasse", short="O")
    competition = await api.create(
        tid,
        "competitions",
        catalog_federation="bds",
        catalog_code="1001",
        range_id=range_["id"],
        fee_first_cents=1000,
        fee_repeat_cents=600,
        max_starts=3,
    )
    definition = copy.deepcopy(competition["definition"])
    definition["variant"]["abschnitte"][0]["serien_gewertet"] = 1
    await api.client.patch(
        f"{API}/tournaments/{tid}/competitions/{competition['id']}", json={"definition": definition}
    )
    own = await api.create(
        tid,
        "competitions",
        name="Vereinsrunde",
        multi_start=False,
        definition={
            "variant": {
                "id": "eigen",
                "name": "Eigen",
                "abschnitte": [{"id": "a", "name": "Wertung", "serien": 3, "schuss_je_serie": 10}],
            },
            "scoring": {"modell": "ringe", "rangfolge": "absteigend", "geprueft": False},
        },
    )
    announcement = (await api.client.get(url)).json()
    for item in announcement["blocks"]:
        if item["id"] == "begruessung":
            item["body"] = "Liebe Schützinnen und Schützen,\n\nwir laden ein."
        if item["id"] == "datenschutz":
            item["visible"] = False
    announcement["facts"]["registration_deadline"] = "2027-03-01"
    # Schießstände ans Ende verschieben, unter eigener ID.
    announcement["blocks"] = [b for b in announcement["blocks"] if b["kind"] != "ranges"]
    announcement["blocks"].append({"id": "staende", "kind": "ranges", "heading": "Schießstände"})
    assert (await api.client.put(url, json=announcement)).status_code == 200

    document = (await api.client.get(f"{url}/document")).json()

    assert document["title"] == "Ausschreibung Vereinspokal"
    assert document["tournament"] == {
        "id": tid,
        "name": "Vereinspokal",
        "organizer": None,
        "date_from": "2027-03-06",
        "date_to": "2027-03-06",
        "status": "draft",
        "currency": "CHF",
    }
    blocks = {b["id"]: b for b in document["blocks"]}
    assert "datenschutz" not in blocks
    assert [b["id"] for b in document["blocks"]][-1] == "staende"
    assert blocks["begruessung"]["body"].startswith("Liebe")
    assert blocks["begruessung"]["competitions"] is None
    assert blocks["termine"]["dates"] == {
        "date_from": "2027-03-06",
        "date_to": "2027-03-06",
        "registration_deadline": "2027-03-01",
    }
    assert blocks["klassen"]["classes"] == [{"name": "Offene Klasse", "short": "O"}]
    assert blocks["staende"]["ranges"] == [
        {
            "range_id": range_["id"],
            "name": "Schießstand 25 m",
            "lane_count": 6,
            "lanes_text": "6 Schützenstände",
        }
    ]
    assert blocks["startgeld"]["fees"] == {
        "currency": "CHF",
        "items": [
            {
                "competition_id": competition["id"],
                "name": "Pistole bis 9 mm",
                "fee_first_cents": 1000,
                "fee_repeat_cents": 600,
            },
            {
                "competition_id": own["id"],
                "name": "Vereinsrunde",
                "fee_first_cents": 0,
                "fee_repeat_cents": None,
            },
        ],
    }
    catalog, custom = blocks["wettbewerbe"]["competitions"]
    assert catalog["catalog_code"] == "1001"
    assert catalog["group"] == "kw-25m-praezision"
    assert catalog["range_name"] == "Schießstand 25 m"
    assert catalog["procedure"] == "20 Schuss: 2×10 in je 5 Min."
    assert catalog["sections"] == [
        {
            "name": "Präzision",
            "serien": 2,
            "schuss_je_serie": 10,
            "serien_gewertet": 1,
            "summary": "Präzision: 2 Serien à 10 Schuss, je 5 Min., gewertet werden die ersten 1",
        }
    ]
    assert catalog["multi_start_text"] == "Bestes Ergebnis zählt (bis zu 3 Starts)"
    # Abweichungen vom Katalog stehen nur im Turnier-Editor (Entscheidung 23.11.2026).
    assert "deviates_from_catalog" not in catalog
    assert "deviations" not in catalog
    diff = await api.client.get(
        f"{API}/tournaments/{tid}/competitions/{competition['id']}/catalog-diff"
    )
    assert diff.json()["deviates"] is True
    # Formelle Wörter: je Wettbewerb die seines Verbands, eigene Disziplin → Standard.
    assert catalog["terms"] == begriffe_fuer("bds").model_dump()
    assert catalog["terms"]["protestgebuehr"] == "Protestgebühr"
    assert custom["terms"] == begriffe.standard().model_dump()
    assert document["terms"] == begriffe_fuer("bds").model_dump()
    assert custom["catalog_code"] is None
    assert custom["multi_start_text"] == "Ein Start je Teilnehmer"


async def test_document_fee_word_by_federation(api: Api) -> None:
    """Ausschreibung: BDS-Wettbewerb „Protestgebühr“ (SHB A 10.04), DSB-Wettbewerb
    „Einspruchsgebühr“ (SpO 0.13); gemischt gilt turnierweit der Standardsatz."""
    tid, url = await tournament(api)
    bds = await api.create(tid, "competitions", catalog_federation="bds", catalog_code="1001")
    response = await api.client.post(
        f"{API}/tournaments/{tid}/competitions",
        json={"catalog_federation": "dsb", "catalog_code": "1.10"},
    )
    if response.status_code != 201:
        pytest.skip(f"DSB-Katalog ohne 1.10 ({response.status_code})")
    dsb = response.json()

    document = (await api.client.get(f"{url}/document")).json()

    block = next(b for b in document["blocks"] if b["kind"] == "competitions")
    terms = {item["id"]: item["terms"] for item in block["competitions"]}
    assert terms[bds["id"]]["gebuehr_einspruch"] == "Protestgebühr"
    assert terms[dsb["id"]]["gebuehr_einspruch"] == "Einspruchsgebühr"
    assert terms[dsb["id"]]["kennziffer"] == "Kennzahl"
    assert terms[dsb["id"]]["ergebnisgleichheit"] == "Ergebnisgleichheit"
    assert document["terms"] == begriffe.standard().model_dump()


def _competition(federation: str | None) -> Competition:
    return Competition(catalog_federation=federation)


def test_document_terms_by_federation() -> None:
    standard = begriffe.standard()
    assert document_terms([]) == standard
    assert document_terms([_competition(None)]) == standard
    assert document_terms([_competition("BDS"), _competition(None)]) == begriffe_fuer("bds")
    # Gemischte Verbände: Standardsatz.
    assert document_terms([_competition("bds"), _competition("dsb")]) == standard
    dsb = document_terms([_competition("dsb")])
    assert dsb.kennziffer == "Kennzahl"
    assert dsb.gebuehr_einspruch == "Einspruchsgebühr"
    assert document_terms([_competition("bds")]).gebuehr_einspruch == "Protestgebühr"


def test_lanes_text() -> None:
    terms = begriffe.standard()
    assert lanes_text(1, terms) == "1 Schützenstand"
    assert lanes_text(6, terms) == "6 Schützenstände"


async def test_active_is_editable_closed_is_locked(api: Api) -> None:
    tid, url = await tournament(api)
    announcement = (await api.client.get(url)).json()

    await api.client.post(f"{API}/tournaments/{tid}/status", json={"status": "active"})
    assert (await api.client.put(url, json=announcement)).status_code == 200
    await api.client.post(f"{API}/tournaments/{tid}/status", json={"status": "closed"})
    locked = await api.client.put(url, json=announcement)

    assert locked.status_code == 409
    assert (await api.client.get(f"{url}/document")).status_code == 200


async def test_unknown_tournament(api: Api) -> None:
    url = f"{API}/tournaments/00000000-0000-0000-0000-000000000000/announcement"

    assert (await api.client.get(url)).status_code == 404
    assert (await api.client.get(f"{url}/document")).status_code == 404
    assert (await api.client.put(url, json={})).status_code == 404


async def test_older_outline_reports_missing_default_blocks(api: Api) -> None:
    """Ältere Turniere haben keinen Abschnitt „Schießstände“: Die App ändert die gespeicherte
    Gliederung nicht, meldet ihn aber zum Hinzufügen."""
    _tid, url = await tournament(api)
    announcement = (await api.client.get(url)).json()
    announcement["blocks"] = [
        b for b in announcement["blocks"] if b["kind"] != "ranges" and b["id"] != "kontakt"
    ]
    # Ein mitgeschicktes `missing_default_blocks` wird beim Speichern ignoriert.
    saved = await api.client.put(url, json=announcement)
    assert saved.status_code == 200, saved.text

    body = (await api.client.get(url)).json()
    assert [(b["id"], b["kind"]) for b in body["missing_default_blocks"]] == [
        ("schiessstaende", "ranges"),
        ("kontakt", "text"),
    ]
    assert saved.json()["missing_default_blocks"] == body["missing_default_blocks"]
    assert "schiessstaende" not in [b["id"] for b in body["blocks"]]
    # Hinzufügen wie angeboten: danach fehlt nichts mehr.
    body["blocks"] += body["missing_default_blocks"]
    assert (await api.client.put(url, json=body)).status_code == 200
    assert (await api.client.get(url)).json()["missing_default_blocks"] == []
