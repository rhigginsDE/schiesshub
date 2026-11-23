"""Siegerliste und Rohexport: Rechenweg bei Wertung mit Zeit, kein Hinweis „Abweichend vom
Katalog“ (nur in der Turnierverwaltung), „Startnummer N“ bei Personen ohne Namensanzeige.

Alle Namen sind erfunden.
"""

from dataclasses import replace
from decimal import Decimal
from typing import Any

from app.modules.export import tables
from app.modules.export.records import TimedSection, TimeScore
from tests.export.conftest import Api, Setup, as_dicts, make_setup, read_csv
from tests.export.pdftext import read_pdf


def export(setup: Setup, name: str) -> str:
    return f"/tournaments/{setup.tid}/export/{name}"


async def person_start(api: Api, setup: Setup, name: str, **person: Any) -> str:
    eid = await api.entry(setup.tid, setup.class_id, name, **person)
    return (await api.starts(setup.tid, eid, setup.cid))[0]


def mehrdistanz(fertigkeit: list[int], parcours: list[int], time_cs: int) -> dict[str, Any]:
    return {
        "sections": {
            "fertigkeit": {"series": [{"sum": value} for value in fertigkeit]},
            "parcours": {"series": [{"sum": value} for value in parcours], "time_cs": time_cs},
        }
    }


def text(score: TimeScore) -> str:
    """Rechenweg mit normalen statt geschützten Leerzeichen."""
    return tables.time_score_text(score).replace(tables.NBSP, " ")


def test_time_score_text_variants() -> None:
    single = TimeScore(
        model="ringe_mit_zeitabzug",
        rings=339,
        time_cs=9340,
        target_s=Decimal(80),
        deduction=Decimal(13),
        sections=(TimedSection("Parcours", 9340, Decimal(80), Decimal(13), False, Decimal(155)),),
    )
    assert text(single) == "339 − 13 (93,40 s, Sollzeit 80 s)"
    # Zahl und Einheit bleiben beim Umbruch zusammen.
    assert "(93,40\u00a0s, Sollzeit\u00a080\u00a0s)" in tables.time_score_text(single)
    missing = replace(
        single,
        time_cs=None,
        deduction=None,
        sections=(TimedSection("Parcours", None, Decimal(80), None, False, Decimal(168)),),
    )
    assert text(missing) == "339 (Zeit fehlt, Sollzeit 80 s)"
    two = replace(
        single,
        sections=(
            TimedSection("A", 9340, Decimal(80), Decimal(13), False, Decimal(155)),
            TimedSection("B", 5000, Decimal("62.5"), Decimal(0), False, Decimal(100)),
        ),
    )
    assert text(two) == "339 − 13 (A 93,40 s, Sollzeit 80 s) − 0 (B 50,00 s, Sollzeit 62,5 s)"
    floored = replace(
        single,
        sections=(TimedSection("Parcours", 9340, Decimal(80), Decimal(13), True, Decimal(0)),),
    )
    assert text(floored).endswith("→ Parcours 0")
    speed = TimeScore("ringe_minus_zeit", 182, 1987, None, Decimal(19), rounded=True)
    assert text(speed) == "182 − 19 (19,87 s, abgerundet)"
    exact = replace(speed, deduction=Decimal("19.87"), rounded=False)
    assert text(exact) == "182 − 19,87 s"


def flat(text: str) -> str:
    """PDF-Text ohne Zeilenwechsel (umbrochene Zellen wieder zusammengesetzt)."""
    return " ".join(text.split())


# --- Mehrdistanz (ringe_mit_zeitabzug) -------------------------------------------------------


async def test_mehrdistanz_shows_time_target_and_deduction(api: Api) -> None:
    setup = await make_setup(
        api, catalog_federation="bds", catalog_code="1201", capture_mode="series"
    )
    over = await person_start(api, setup, "Konrad Probst", club="SV Nord")
    exact = await person_start(api, setup, "Greta Probe", club="SV Süd")
    # 45+44+42+40 + 46+43+41+38 = 339; 93,40 s bei Sollzeit 80 s → 13 Ringe Abzug → 326
    await api.shoot(setup.tid, over, mehrdistanz([45, 44, 42, 40], [46, 43, 41, 38], 9340))
    # 320 Ringe, 81,00 s → 1 Ring Abzug → 319
    await api.shoot(setup.tid, exact, mehrdistanz([40] * 4, [40] * 4, 8100))

    rows = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    first, second = rows
    assert first["Name"] == "Konrad Probst"
    assert first["Ergebnis"] == "326"
    assert first["Ringe vor Abzug"] == "339"
    assert first["Gesamtzeit"] == "93,40"
    assert first["Sollzeit"] == "80"
    assert first["Abzug"] == "13"
    assert (second["Ergebnis"], second["Ringe vor Abzug"], second["Gesamtzeit"]) == (
        "319",
        "320",
        "81,00",
    )
    assert second["Abzug"] == "1"

    pdf = read_pdf((await api.get(export(setup, "winners.pdf"))).content)
    text = flat(pdf.text)
    assert "339 − 13 (93,40 s, Sollzeit 80 s)" in text
    assert "320 − 1 (81,00 s, Sollzeit 80 s)" in text
    assert "Rechenweg" in text

    raw = as_dicts(read_csv((await api.get(export(setup, "results.csv"))).content))
    by_name = {row["Name"]: row for row in raw}
    karl = by_name["Konrad Probst"]
    assert karl["Ergebnis"] == "326"
    assert karl["Ringe vor Abzug"] == "339"
    assert karl["Gesamtzeit"] == "93,40"
    assert karl["Sollzeit"] == "80"
    assert karl["Abzug"] == "13"
    assert karl["Serie 8 Ringe"] == "38"


async def test_mehrdistanz_within_target_time(api: Api) -> None:
    setup = await make_setup(
        api, catalog_federation="bds", catalog_code="1201", capture_mode="series"
    )
    sid = await person_start(api, setup, "Ida Muster")
    await api.shoot(setup.tid, sid, mehrdistanz([44, 43, 41, 40], [45, 42, 40, 39], 7890))
    (row,) = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    assert (row["Ergebnis"], row["Gesamtzeit"], row["Abzug"]) == ("334", "78,90", "0")
    text = flat(read_pdf((await api.get(export(setup, "winners.pdf"))).content).text)
    assert "334 − 0 (78,90 s, Sollzeit 80 s)" in text


# --- Speed (ringe_minus_zeit) ----------------------------------------------------------------


async def test_speed_shows_time_sum_and_deduction(api: Api) -> None:
    setup = await make_setup(
        api, catalog_federation="bds", catalog_code="1401", capture_mode="series"
    )
    sid = await person_start(api, setup, "Lene Beispiel")
    raw = {
        "sections": {
            "speed": {
                "series": [
                    {"sum": 50, "time_cs": 512},
                    {"sum": 47, "time_cs": 480},
                    {"sum": 44, "time_cs": 505},
                    {"sum": 41, "time_cs": 490},
                ]
            }
        }
    }
    await api.shoot(setup.tid, sid, raw)
    # 182 Ringe − ⌊19,87 s⌋ = 163
    (row,) = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    assert row["Ergebnis"] == "163"
    assert row["Ringe vor Abzug"] == "182"
    assert row["Gesamtzeit"] == "19,87"
    assert row["Sollzeit"] == ""
    assert row["Abzug"] == "19"
    text = flat(read_pdf((await api.get(export(setup, "winners.pdf"))).content).text)
    assert "182 − 19 (19,87 s, abgerundet)" in text
    (raw_row,) = as_dicts(read_csv((await api.get(export(setup, "results.csv"))).content))
    assert raw_row["Gesamtzeit"] == "19,87"
    assert raw_row["Abzug"] == "19"
    assert raw_row["Serie 1 Zeit"] == "5,12"


# --- Andere Modelle bleiben, wie sie sind ----------------------------------------------------


async def test_ring_model_has_no_time_columns(api: Api) -> None:
    setup = await make_setup(api)
    sid = await person_start(api, setup, "Anna Beispiel")
    await api.shoot(
        setup.tid, sid, {"sections": {"praezision": {"series": [{"shots": [9] * 5}] * 2}}}
    )
    header = read_csv((await api.get(export(setup, "winners.csv"))).content)[0]
    for column in ("Ringe vor Abzug", "Gesamtzeit", "Sollzeit", "Abzug"):
        assert column not in header
    assert "Abweichend vom Katalog" not in header
    raw_header = read_csv((await api.get(export(setup, "results.csv"))).content)[0]
    assert "Gesamtzeit" not in raw_header
    lines = read_pdf((await api.get(export(setup, "winners.pdf"))).content).text.splitlines()
    assert "Rechenweg" not in lines
    assert not any("Abweichend vom Katalog" in line for line in lines)


# --- Abweichend vom Katalog: nur in der Turnierverwaltung ------------------------------------


async def test_catalog_deviation_not_in_lists(api: Api) -> None:
    """Entscheidung vom 22.11.2026: Abweichungen zeigt nur die Turnierverwaltung, nicht die
    Siegerliste und nicht der Rohexport."""
    tid = await api.tournament()
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    cid = await api.competition(
        tid, range_id, catalog_federation="bds", catalog_code="4401", capture_mode="series"
    )
    competition = await api.ok("GET", f"/tournaments/{tid}/competitions/{cid}")
    definition = competition["definition"]
    definition["variant"]["abschnitte"][0]["serien_gewertet"] = 3
    await api.ok("PATCH", f"/tournaments/{tid}/competitions/{cid}", json={"definition": definition})
    await api.activate(tid)
    setup = Setup(tid, range_id, class_id, cid)
    sid = await person_start(api, setup, "Otto Beispiel")
    series = [{"time_cs": 1000, "standing": 0} for _ in range(4)]
    await api.shoot(tid, sid, {"sections": {"fallscheibe": {"series": series}}})

    # Die Abweichung selbst gibt es (Turnierverwaltung) ...
    diff = await api.ok("GET", f"/tournaments/{tid}/competitions/{cid}/catalog-diff")
    assert diff["deviates"] is True

    # ... aber weder Siegerliste noch Rohexport erwähnen sie.
    for name in ("winners.csv", "results.csv"):
        content = (await api.get(export(setup, name))).content
        header = read_csv(content)[0]
        assert "Abweichend vom Katalog" not in header, name
        assert "Serien gewertet" not in content.decode("utf-8-sig"), name
    text = flat(read_pdf((await api.get(export(setup, "winners.pdf"))).content).text)
    assert "Abweichend vom Katalog" not in text
    assert "Serien gewertet" not in text
    assert "4401 · " in text


# --- „nicht anzeigen“: Startnummer statt leerem Namen ----------------------------------------


async def test_hidden_person_shows_start_number(api: Api) -> None:
    setup = await make_setup(api)
    sid = await person_start(api, setup, "Łukasz Čapek", display_mode="hidden")
    await api.shoot(
        setup.tid, sid, {"sections": {"praezision": {"series": [{"shots": [9] * 5}] * 2}}}
    )
    for name in ("winners.csv", "results.csv", "startlist.csv"):
        (row,) = as_dicts(read_csv((await api.get(export(setup, name))).content))
        assert row["Name"] == "Startnummer 1", name
    for name in ("winners.pdf", "startlist.pdf"):
        text = flat(read_pdf((await api.get(export(setup, name))).content).text)
        assert "Startnummer 1" in text, name
        assert "Čapek" not in text
    full = as_dicts(read_csv((await api.get(export(setup, "winners.csv"), names="full")).content))
    assert full[0]["Name"] == "Łukasz Čapek"
