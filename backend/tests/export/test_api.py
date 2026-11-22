"""Endpunkte des Exports: Dateien, Namensregeln, Rechte, Siegerliste, Rohexport, leere Turniere.

Alle Namen sind erfunden.
"""

import re
from collections.abc import Callable
from typing import Any

import pytest

from app.modules.export.fonts import DEJAVU_DIR
from tests.export.conftest import (
    Api,
    Setup,
    as_dicts,
    make_setup,
    precision_definition,
    read_csv,
    shots,
)
from tests.export.pdftext import read_pdf

PEOPLE = (
    # Name, Verein, Anzeige, Verein anzeigen
    ("Deniz Yılmaz", "SV Nord", "short", True),
    ("Jürgen Maier", "SV Süd", "full", False),
    ("Łukasz Čapek", "SV Ost", "hidden", True),
)


def export(setup: Setup, name: str) -> str:
    return f"/tournaments/{setup.tid}/export/{name}"


async def person_start(api: Api, setup: Setup, name: str, **person: Any) -> str:
    eid = await api.entry(setup.tid, person.pop("class_id", setup.class_id), name, **person)
    return (await api.starts(setup.tid, eid, setup.cid, person.pop("count", 1)))[0]


async def three_people(api: Api, setup: Setup) -> list[str]:
    starts = []
    for name, club, mode, show in PEOPLE:
        starts.append(
            await person_start(api, setup, name, club=club, display_mode=mode, show_club=show)
        )
    return starts


# --- Startliste ------------------------------------------------------------------------------


async def test_startlist_csv_public_names(api: Api) -> None:
    setup = await make_setup(
        api, catalog_federation="bds", catalog_code="4401", capture_mode="series"
    )
    await three_people(api, setup)
    response = await api.get(export(setup, "startlist.csv"))
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="Vereinspokal-2027_Startliste_2027-03-06.csv"'
    )
    assert response.headers["cache-control"] == "no-store"
    rows = as_dicts(read_csv(response.content))
    assert [(r["Startnummer"], r["Name"], r["Verein"]) for r in rows] == [
        ("1", "D. Yılmaz", "SV Nord"),
        ("2", "Jürgen Maier", ""),
        ("3", "", "SV Ost"),
    ]
    assert rows[0]["Kennziffer"] == "4401"
    assert rows[0]["Stand"] == "Stand 1"
    assert rows[0]["Status"] == "angemeldet"
    assert list(rows[0]) == [
        "Startnummer",
        "Name",
        "Verein",
        "Klasse",
        "Klassenname",
        "Kennziffer",
        "Wettbewerb",
        "Stand",
        "Versuch",
        "Durchgang",
        "Beginn",
        "Bahn",
        "Reihenfolge",
        "Status",
        "Abbruchgrund",
    ]


async def test_startlist_full_names(api: Api) -> None:
    setup = await make_setup(api)
    await three_people(api, setup)
    rows = as_dicts(read_csv((await api.get(export(setup, "startlist.csv"), names="full")).content))
    assert [(r["Name"], r["Verein"]) for r in rows] == [
        ("Deniz Yılmaz", "SV Nord"),
        ("Jürgen Maier", "SV Süd"),
        ("Łukasz Čapek", "SV Ost"),
    ]


async def test_startlist_pdf_contains_names(api: Api) -> None:
    setup = await make_setup(api)
    await three_people(api, setup)
    response = await api.get(export(setup, "startlist.pdf"), names="full")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].endswith('_Startliste_2027-03-06.pdf"')
    pdf = read_pdf(response.content)
    assert len(pdf.pages) == 1
    text = pdf.text
    assert "Startliste" in text
    assert "Vereinspokal 2027" in text
    assert "Veranstalter: SV Musterstadt · 06.03.2027" in text
    assert "Interne Liste mit vollen Namen" in text
    assert "Seite 1 von 1" in text
    assert "erstellt mit Schiesshub" in text
    if (DEJAVU_DIR / "DejaVuSans.ttf").is_file():
        for name, *_ in PEOPLE:
            assert name in text
    public = read_pdf((await api.get(export(setup, "startlist.pdf"))).content).text
    assert "D. Yılmaz" in public
    assert "Deniz" not in public
    assert "Łukasz" not in public
    assert "Čapek" not in public
    assert "Interne Liste" not in public


async def test_startlist_sort_and_filters(api: Api) -> None:
    setup = await make_setup(api)
    other_range = await api.range(setup.tid, "Stand 2")
    other = await api.competition(
        setup.tid,
        other_range,
        name="Zweiter",
        definition=precision_definition(),
        capture_mode="shot",
    )
    first = await api.entry(setup.tid, setup.class_id, "Anna Beispiel")
    second = await api.entry(setup.tid, setup.class_id, "Bernd Beispiel")
    await api.starts(setup.tid, second, setup.cid)
    await api.starts(setup.tid, first, other)
    await api.starts(setup.tid, first, setup.cid)

    def numbers(content: bytes) -> list[tuple[str, str]]:
        return [(r["Startnummer"], r["Wettbewerb"]) for r in as_dicts(read_csv(content))]

    by_number = (await api.get(export(setup, "startlist.csv"), sort="start_number")).content
    assert numbers(by_number) == [("1", "Wettbewerb"), ("1", "Zweiter"), ("2", "Wettbewerb")]
    only = (await api.get(export(setup, "startlist.csv"), competition_id=other)).content
    assert numbers(only) == [("1", "Zweiter")]
    by_range = (await api.get(export(setup, "startlist.csv"), range_id=other_range)).content
    assert numbers(by_range) == [("1", "Zweiter")]
    text = read_pdf((await api.get(export(setup, "startlist.pdf"), sort="range")).content).text
    assert text.index("Stand 1") < text.index("Stand 2")


# --- Rechte ---------------------------------------------------------------------------------


async def test_full_names_need_permission(api: Api, grant: Callable[..., None]) -> None:
    setup = await make_setup(api)
    await three_people(api, setup)
    grant("export.read")
    for name in ("startlist.csv", "startlist.pdf", "winners.csv", "winners.pdf", "results.csv"):
        response = await api.client.get(f"/api/v1{export(setup, name)}", params={"names": "full"})
        assert response.status_code == 403, name
        assert "export.full_names" in response.json()["detail"]
        assert (await api.client.get(f"/api/v1{export(setup, name)}")).status_code == 200
    grant("export.read", "export.full_names")
    await api.get(export(setup, "startlist.csv"), names="full")
    grant()
    response = await api.client.get(f"/api/v1{export(setup, 'startlist.csv')}")
    assert response.status_code == 403
    assert "export.read" in response.json()["detail"]


async def test_permissions_in_manifest(api: Api) -> None:
    from app.modules import MODULES

    export_module = next(m for m in MODULES if m.name == "export")
    assert export_module.permissions == ("export.read", "export.full_names")


# --- Siegerliste -----------------------------------------------------------------------------


async def test_winners_ties_aborted_and_columns(api: Api) -> None:
    setup = await make_setup(api)
    a = await person_start(api, setup, "Anna Beispiel", club="SV Nord")
    b = await person_start(api, setup, "Bernd Beispiel", club="SV Nord")
    c = await person_start(api, setup, "Clara Beispiel", club="SV Süd")
    d = await person_start(api, setup, "Dora Beispiel")
    e = await person_start(api, setup, "Emil Beispiel")
    f = await person_start(api, setup, "Frida Beispiel")
    await api.shoot(setup.tid, a, shots([10] * 5, [9] * 5))  # 95
    # Gleichstand ohne Zehner-Unterschied: geteilter Platz
    await api.shoot(setup.tid, b, shots([10, 10, 9, 9, 9], [9] * 5))  # 92, 2 Zehner
    await api.shoot(setup.tid, c, shots([9, 9, 9, 10, 10], [9] * 5))  # 92, 2 Zehner
    await api.abort(setup.tid, d, "dns")
    await api.abort(setup.tid, e, "dsq")
    await api.shoot(setup.tid, f, shots([8] * 5), final=False)
    await api.abort(setup.tid, f, "dnf")

    rows = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    assert [(r["Platz"], r["Platz geteilt"], r["Name"], r["Status"]) for r in rows] == [
        ("1", "", "Anna Beispiel", "endgültig"),
        ("2", "ja", "Bernd Beispiel", "endgültig"),
        ("2", "ja", "Clara Beispiel", "endgültig"),
        # Abgebrochene: nie mit Platz, am Ende (aufgegeben, nicht angetreten, disqualifiziert).
        ("", "", "Frida Beispiel", "aufgegeben"),
        ("", "", "Dora Beispiel", "nicht angetreten"),
        ("", "", "Emil Beispiel", "disqualifiziert"),
    ]
    assert rows[0]["Ergebnis"] == "95"
    assert rows[0]["Einheit"] == "Ringe"
    assert rows[0]["Zehner"] == "5"
    assert rows[0]["Teilwerte"] == "50; 45"
    assert rows[0]["Wertung"] == "Klasse offen"

    pdf = read_pdf((await api.get(export(setup, "winners.pdf"))).content)
    text = pdf.text
    assert "Siegerliste" in text
    assert "Klasse offen" in text
    lines = text.splitlines()
    assert (
        lines.index("Anna Beispiel") < lines.index("Bernd Beispiel") < lines.index("Dora Beispiel")
    )
    assert "nicht angetreten" in text
    assert "disqualifiziert" in text
    assert "aufgegeben" in text
    for header in ("Platz", "Nr.", "Name", "Verein", "Ergebnis (Ringe)", "S1", "S2"):
        assert header in lines

    top = as_dicts(read_csv((await api.get(export(setup, "winners.csv"), top=2)).content))
    assert [r["Name"] for r in top] == ["Anna Beispiel", "Bernd Beispiel", "Clara Beispiel"]
    assert (
        len(as_dicts(read_csv((await api.get(export(setup, "winners.csv"), top="")).content))) == 6
    )


async def test_winners_multi_start_and_merged_classes(api: Api) -> None:
    setup = await make_setup(api, multi_start=True, max_starts=2, multi_start_rule="best")
    ladies = await api.klass(setup.tid, "damen", merge_into_id=setup.class_id)
    eid = await api.entry(setup.tid, setup.class_id, "Anna Beispiel")
    first, second = await api.starts(setup.tid, eid, setup.cid, count=2)
    lady = await person_start(api, setup, "Berta Beispiel", class_id=ladies)
    await api.shoot(setup.tid, first, shots([8] * 5, [8] * 5))
    await api.shoot(setup.tid, second, shots([10] * 5, [9] * 5))
    await api.shoot(setup.tid, lady, shots([9] * 5, [9] * 5))

    separate = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    assert [
        (r["Wertung"], r["Platz"], r["Name"], r["Versuch"], r["Ergebnis"]) for r in separate
    ] == [
        ("Klasse offen", "1", "Anna Beispiel", "2", "95"),
        ("Klasse damen", "1", "Berta Beispiel", "1", "90"),
    ]
    merged = as_dicts(
        read_csv((await api.get(export(setup, "winners.csv"), merged="true")).content)
    )
    assert [(r["Wertung"], r["Platz"], r["Klasse"]) for r in merged] == [
        ("Klasse offen (zusammengelegt mit Klasse damen)", "1", "OFF"),
        ("Klasse offen (zusammengelegt mit Klasse damen)", "2", "DAM"),
    ]
    only = as_dicts(
        read_csv((await api.get(export(setup, "winners.csv"), class_id=ladies)).content)
    )
    assert [r["Name"] for r in only] == ["Berta Beispiel"]
    text = read_pdf((await api.get(export(setup, "winners.pdf"), merged="true")).content).text
    assert "Versuch" in text.splitlines()
    assert "Klasse" in text.splitlines()


async def test_winners_provisional_note(api: Api) -> None:
    setup = await make_setup(api, tournament={"protest_minutes": 30})
    sid = await person_start(api, setup, "Anna Beispiel")
    await api.shoot(setup.tid, sid, shots([9] * 5, [9] * 5))
    rows = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    assert rows[0]["Status"] == "vorläufig"
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d", rows[0]["Vorläufig bis"])
    text = read_pdf((await api.get(export(setup, "winners.pdf"))).content).text
    assert re.search(
        r"Vorläufig – Einspruchsfrist läuft bis (\d\d\.\d\d\.\d{4}, )?\d\d:\d\d Uhr", text
    )

    without = await api.get(export(setup, "winners.pdf"), include_provisional="false")
    text = read_pdf(without.content).text
    assert "Anna Beispiel" not in text
    assert "Für diese Auswahl gibt es noch keine Ergebnisse." in text
    assert (
        read_csv(
            (await api.get(export(setup, "winners.csv"), include_provisional="false")).content
        )[1:]
        == []
    )


async def test_winners_struck_series_and_all_competitions(api: Api) -> None:
    setup = await make_setup(api, definition=precision_definition(series=3, counted=2))
    other = await api.competition(
        setup.tid, setup.range_id, name="Ohne Ergebnis", definition=precision_definition()
    )
    eid = await api.entry(setup.tid, setup.class_id, "Anna Beispiel")
    sid = (await api.starts(setup.tid, eid, setup.cid))[0]
    await api.starts(setup.tid, eid, other)
    await api.shoot(setup.tid, sid, shots([10] * 5, [9] * 5, [8] * 5))
    rows = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    assert [(r["Wettbewerb"], r["Ergebnis"], r["Teilwerte"]) for r in rows] == [
        ("Wettbewerb", "95", "50; 45; (40)")
    ]
    text = read_pdf((await api.get(export(setup, "winners.pdf"))).content).text
    assert "(40)" in text
    assert "gestrichene Serie" in text
    assert "Ohne Ergebnis" not in text
    single = await api.get(export(setup, "winners.pdf"), competition_id=other)
    assert "Noch keine abgeschlossenen Ergebnisse." in read_pdf(single.content).text or (
        "Für diese Auswahl gibt es noch keine Ergebnisse." in read_pdf(single.content).text
    )


# --- Rohexport -------------------------------------------------------------------------------


async def test_results_csv_series_columns(api: Api) -> None:
    setup = await make_setup(
        api, catalog_federation="bds", catalog_code="4401", capture_mode="series"
    )
    sid = await person_start(api, setup, "Anna Beispiel", club='=HYPERLINK("x")')
    open_ = await person_start(api, setup, "Bernd Beispiel")
    raw = {
        "sections": {
            "fallscheibe": {
                "series": [
                    {"time_cs": 1284, "standing": 1},
                    {"time_cs": 990, "standing": 0},
                    {"time_cs": 1100, "standing": 0},
                    {"time_cs": 1000, "standing": 2},
                ]
            }
        }
    }
    await api.shoot(setup.tid, sid, raw)
    response = await api.get(export(setup, "results.csv"), names="full")
    assert response.headers["content-disposition"].endswith('_Ergebnisse_2027-03-06.csv"')
    table = read_csv(response.content)
    rows = as_dicts(table)
    assert [r["Startnummer"] for r in rows] == ["1", "2"]
    first, second = rows
    assert first["Verein"] == '\'=HYPERLINK("x")'
    assert first["Kennziffer"] == "4401"
    assert first["Status"] == "abgeschlossen"
    assert first["Einheit"] == "s"
    assert first["Serie 1 Zeit"] == "12,84"
    assert first["Serie 1 Zeit mit Zuschlag"] == "22,84"
    assert first["Serie 1 Stehend"] == "1"
    assert first["Serie 4 Zeit mit Zuschlag"] == "30,00"
    assert first["Ergebnis"] == "73,74"
    assert "Serie 1 Ringe" not in first
    assert first["Abgeschlossen am"]
    assert second["Name"] == "Bernd Beispiel"
    assert second["Ergebnis"] == ""
    assert second["Status"] == "angemeldet"
    assert open_  # zweiter Start ohne Ergebnis steht trotzdem in der Datei


async def test_results_csv_rings_and_struck(api: Api) -> None:
    setup = await make_setup(api, definition=precision_definition(series=3, counted=2))
    sid = await person_start(api, setup, "Anna Beispiel")
    await api.shoot(setup.tid, sid, shots([10, 10, "X", 9, 9], [9] * 5, [8] * 5))
    (row,) = as_dicts(read_csv((await api.get(export(setup, "results.csv"))).content))
    assert row["Name"] == "Anna Beispiel"
    assert (row["Serie 1 Ringe"], row["Serie 2 Ringe"], row["Serie 3 Ringe"]) == ("48", "45", "40")
    assert row["Gestrichene Serien"] == "3"
    assert row["Ergebnis"] == "93"
    assert row["Zehner"] == "3"
    assert row["Innenzehner"] == "1"
    assert row["Vollständig"] == "ja"


# --- Grenzfälle ------------------------------------------------------------------------------


async def test_empty_tournament(api: Api) -> None:
    tid = await api.tournament(name="Leeres Turnier")
    base = f"/tournaments/{tid}/export"
    for name, hint in (("startlist.pdf", "keine Starts"), ("winners.pdf", "keine Ergebnisse")):
        pdf = read_pdf((await api.get(f"{base}/{name}")).content)
        assert len(pdf.pages) == 1
        assert "Leeres Turnier" in pdf.text
        assert hint in pdf.text
    for name in ("startlist.csv", "winners.csv", "results.csv"):
        table = read_csv((await api.get(f"{base}/{name}")).content)
        assert len(table) == 1
        assert table[0][0]


async def test_not_found_and_invalid(api: Api) -> None:
    setup = await make_setup(api)
    other = await make_setup(api)
    missing = "00000000-0000-0000-0000-000000000000"
    await api.get(export(setup, "winners.pdf"), 404, competition_id=other.cid)
    await api.get(export(setup, "winners.csv"), 404, class_id=other.class_id)
    await api.get(export(setup, "startlist.csv"), 404, range_id=other.range_id)
    await api.get(f"/tournaments/{missing}/export/startlist.pdf", 404)
    response = await api.get(export(setup, "winners.csv"), 422, top=0)
    assert "top" in response.json()["detail"]
    await api.get(export(setup, "startlist.csv"), 422, names="alle")
    await api.get(export(setup, "startlist.csv"), 200, competition_id="")


@pytest.mark.skipif(
    not (DEJAVU_DIR / "DejaVuSans.ttf").is_file(),
    reason="DejaVu Sans fehlt im Image (Paket fonts-dejavu-core, deploy/backend.Dockerfile)",
)
async def test_pdf_embeds_unicode_font(api: Api) -> None:
    setup = await make_setup(api)
    starts = await three_people(api, setup)
    for sid, points in zip(starts, (9, 8, 7), strict=True):
        await api.shoot(setup.tid, sid, shots([points] * 5, [points] * 5))
    pdf = read_pdf((await api.get(export(setup, "winners.pdf"), names="full")).content)
    assert any("DejaVuSans" in font for font in pdf.fonts)
    assert pdf.embedded_fonts >= 1
    lines = pdf.text.splitlines()
    assert lines[lines.index("Deniz Yılmaz") - 2 : lines.index("Deniz Yılmaz") + 2] == [
        "1.",
        "1",
        "Deniz Yılmaz",
        "SV Nord",
    ]
    assert "Jürgen Maier" in lines
    assert "Łukasz Čapek" in lines
