"""Formelle Begriffe je Verband: Dateien, Rückfall und `GET /terms`."""

from pathlib import Path

import httpx
import pytest
import yaml

from app.core import begriffe
from app.core.begriffe import (
    DIRECTORY,
    KEYS,
    STANDARD,
    Begriffe,
    BegriffeFehler,
    begriffe_fuer,
    load,
)

API = "/api/v1"
FILES = sorted(DIRECTORY.glob("*.yaml"))


def _words(path: Path) -> dict[str, str]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["begriffe"] or {}


def test_files_exist() -> None:
    assert {path.stem for path in FILES} >= {STANDARD, "bds", "dsb"}


def test_standard_has_every_key() -> None:
    assert set(_words(DIRECTORY / f"{STANDARD}.yaml")) == KEYS


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.name)
def test_no_unknown_keys_and_no_empty_words(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert set(data) == {"begriffe"}
    words = data["begriffe"] or {}
    assert set(words) <= KEYS
    assert all(isinstance(value, str) and value.strip() for value in words.values())


def test_standard_is_bds_wording() -> None:
    """Entscheidung 23.11.2026: Standard = Wörter des BDS-Sporthandbuchs."""
    standard = begriffe.standard()
    assert begriffe_fuer("bds") == standard
    assert standard.schuetzenstand == "Schützenstand"
    assert standard.schiessstand == "Schießstand"
    assert standard.ergebnisliste == "Ergebnisliste"
    assert standard.protestgebuehr == "Protestgebühr"
    assert standard.ringgleichheit == "Ringgleichheit"
    assert standard.durchgangszeit == "Durchgangszeit"
    assert (standard.abbruch, standard.abbruch_kurz) == ("Abbruch", "AB")


def test_bds_words_have_a_source() -> None:
    """Jedes BDS-Wort steht mit Fundstelle als Kommentar darüber."""
    lines = (DIRECTORY / "bds.yaml").read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if line.startswith("  ") and not stripped.startswith("#") and ":" in stripped:
            above = [entry.strip() for entry in lines[:index] if entry.strip()]
            assert above[-1].startswith("#") or ":" in above[-1], line


def test_fallback() -> None:
    standard = begriffe.standard()
    assert begriffe_fuer(None) == standard
    assert begriffe_fuer("") == standard
    assert begriffe_fuer("unbekannt") == standard
    # Groß/klein egal, wie `catalog_federation` gerade geschrieben ist.
    assert begriffe_fuer("DSB") == begriffe_fuer("dsb")
    dsb = begriffe_fuer("dsb")
    assert dsb.kennziffer == "Kennzahl"
    # Beim DSB nicht belegt: kommt aus dem Standard.
    assert dsb.durchgangszeit == standard.durchgangszeit


def test_dsb_marks_missing_terms() -> None:
    """Was dsb.yaml nicht nennt, steht dort als „nicht belegt“ (Rückfall auf den Standard)."""
    text = (DIRECTORY / "dsb.yaml").read_text(encoding="utf-8")
    note = text.split("# Nicht belegt", 1)[1]
    missing = KEYS - set(_words(DIRECTORY / "dsb.yaml"))
    for key in missing:
        assert key in note, f"{key} fehlt in der Liste der nicht belegten DSB-Begriffe"


def test_dsb_words_from_sportordnung() -> None:
    """DSB-Sportordnung 2027 (dsb-begriffe.md): eigene Wörter, keine Kurzform „AB“."""
    dsb = begriffe_fuer("dsb")
    assert dsb.ergebnisgleichheit == "Ergebnisgleichheit"  # SpO 0.12
    assert dsb.gebuehr_einspruch == "Einspruchsgebühr"  # SpO 0.13
    assert dsb.kennziffer == "Kennzahl"  # SpO 0.21
    assert dsb.klasse == "Wettkampfklasse"  # SpO 0.7.1
    assert dsb.wertungsserie == "Wettkampfserie"  # SpO 0.9.8.2
    assert dsb.wertungsschuesse == "Wettkampfschüsse"  # SpO 0.21
    assert dsb.startzeit == "Startzeit"  # SpO 0.7.5.2
    assert dsb.nicht_angetreten == "nicht angetreten"  # SpO 0.15
    assert "AB" not in (dsb.abbruch, dsb.abbruch_kurz)
    bds = begriffe_fuer("bds")
    assert bds.gebuehr_einspruch == "Protestgebühr"  # SHB A 10.04
    assert bds.klasse == "Wettbewerbsklasse"  # SHB A 3.08
    assert bds.startzeit == "Starttermin"  # SHB A 7.05


# --- Prüfung beim Laden ---------------------------------------------------------------


def _write(directory: Path, name: str, words: dict[str, str]) -> None:
    (directory / f"{name}.yaml").write_text(
        yaml.safe_dump({"begriffe": words}, allow_unicode=True), encoding="utf-8"
    )


def _full() -> dict[str, str]:
    return begriffe.standard().model_dump()


def test_load_merges_federation_over_standard(tmp_path: Path) -> None:
    _write(tmp_path, STANDARD, _full())
    _write(tmp_path, "xyz", {"kennziffer": "Nummer"})
    standard, federations = load(tmp_path)
    assert federations["xyz"].kennziffer == "Nummer"
    assert federations["xyz"].schuetzenstand == standard.schuetzenstand


def test_load_rejects_missing_standard_key(tmp_path: Path) -> None:
    words = _full()
    del words["ergebnisliste"]
    _write(tmp_path, STANDARD, words)
    with pytest.raises(BegriffeFehler, match="ergebnisliste"):
        load(tmp_path)


def test_load_rejects_unknown_key(tmp_path: Path) -> None:
    _write(tmp_path, STANDARD, _full())
    _write(tmp_path, "xyz", {"bahn": "Bahn"})
    with pytest.raises(BegriffeFehler, match="unbekannte Schlüssel bahn"):
        load(tmp_path)


def test_load_rejects_empty_word(tmp_path: Path) -> None:
    _write(tmp_path, STANDARD, _full())
    _write(tmp_path, "xyz", {"startgeld": "  "})
    with pytest.raises(BegriffeFehler, match="startgeld"):
        load(tmp_path)


def test_model_lists_every_key() -> None:
    assert set(Begriffe.model_fields) == KEYS


# --- Endpunkt -------------------------------------------------------------------------


async def test_terms_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{API}/terms")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"default", "federations"}
    assert set(body["default"]) == KEYS
    assert body["default"]["schuetzenstand"] == "Schützenstand"
    assert {"bds", "dsb"} <= set(body["federations"])
    for terms in body["federations"].values():
        assert set(terms) == KEYS
    assert body["federations"]["dsb"]["kennziffer"] == "Kennzahl"
    assert body["federations"]["bds"] == body["default"]


async def test_terms_in_openapi(client: httpx.AsyncClient) -> None:
    schema = (await client.get(f"{API}/openapi.json")).json()
    operation = schema["paths"][f"{API}/terms"]["get"]
    assert operation["summary"] == "Formelle Begriffe je Verband"
    assert "Schützenstand" in operation["description"]
    assert set(schema["components"]["schemas"]["Begriffe"]["properties"]) == KEYS
