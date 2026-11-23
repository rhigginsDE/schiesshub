"""Kompletter Weg mit Zehntelwertung und DSB-Gleichstandskette: Maske, Erfassen (Komma und
Punkt), Prüfung, Abschließen, Korrektur mit Verlauf, Rangliste mit Stechen und Hinweis."""

from typing import Any

from tests.ergebnisse.conftest import Api, make_setup


def tenths_definition() -> dict[str, Any]:
    return {
        "variant": {
            "id": "standard",
            "name": "Standard",
            "wettkampfzeit_gesamt_s": 3600,
            "abschnitte": [
                {
                    "id": "lg",
                    "name": "Luftgewehr",
                    "serien": 2,
                    "schuss_je_serie": 2,
                    "wettkampfzeit_s": 3000,
                    "vorbereitung_probe_s": 900,
                    "probeschuesse": "unbegrenzt",
                }
            ],
        },
        "scoring": {
            "modell": "ringe",
            "rangfolge": "absteigend",
            "zehntelwertung": True,
            "gleichstand": ["stechen", "letzte_serie_rueckwaerts", "zehner", "mouchen"],
            "stechen_bis_platz": 1,
            "geprueft": False,
        },
    }


def raw(*series: list[Any]) -> dict[str, Any]:
    return {"sections": {"lg": {"series": [{"shots": list(s)} for s in series]}}}


async def test_tenths_full_path(api: Api) -> None:
    setup = await make_setup(api, definition=tenths_definition(), capture_mode="shot")
    starts = []
    for _ in range(5):
        eid = await api.entry(setup.tid, setup.class_id)
        starts.append((await api.starts(setup.tid, eid, setup.cid))[0])
    path = api.start_path(setup.tid, starts[0])

    form = (await api.ok("GET", f"{path}/form"))["form"]
    shots = form["sections"][0]["series"][0]["fields"][0]
    assert (shots["decimals"], shots["step"], shots["value_max"]) == (1, "0.1", "10.9")
    assert form["ring_decimals"] == 1
    assert form["shootoff_until_place"] == 1
    assert form["competition_time_total_s"] == "3600"
    assert "Probeschüsse unbegrenzt" in form["sections"][0]["hints"]

    # Ungültige Werte: deutsche Meldung mit Pfad, nichts gespeichert.
    await api.call(setup.tid, starts[0])
    body = await api.fail(
        "PUT", f"{path}/raw", 422, json={"raw": raw(["10,95", 11.0]), "base_seq": 0}
    )
    assert [e["field"] for e in body["errors"]] == [
        "raw.sections.lg.series[0].shots[0]",
        "raw.sections.lg.series[0].shots[1]",
    ]
    assert (
        "Bei Zehntelwertung sind Werte von 1,0 bis 10,9 oder 0 erlaubt."
        in (body["errors"][1]["message"])
    )

    # Komma und Punkt, Text und Zahl gemischt.
    state = await api.put_raw(setup.tid, starts[0], raw(["10,5", 9.8], [10.0, "9.9"]), 0)
    assert state["computed"]["score_text"] == "40,2 Ringe"
    assert state["score"] == "40.2"
    assert state["raw"]["sections"]["lg"]["series"][0]["shots"] == ["10,5", 9.8]
    state = await api.finalize(setup.tid, starts[0], state["seq"])
    assert state["is_final"]

    # Korrektur: neues Ereignis, Verlauf mit Unterschied.
    corrected = await api.ok(
        "POST",
        f"{path}/correct",
        json={
            "raw": raw(["10,5", 9.8], [10.0, "10,1"]),
            "reason": "Auswertung Schuss 4",
            "base_seq": state["seq"],
        },
    )
    assert corrected["computed"]["score_text"] == "40,4 Ringe"
    events = await api.ok("GET", f"{path}/events")
    assert [e["type"] for e in events] == ["raw_set", "finalized", "corrected"]
    assert events[2]["changes"] == [
        {
            "path": "sections.lg.series[1].shots",
            "before": [10.0, "9.9"],
            "after": [10.0, "10,1"],
        }
    ]

    # Zwei mit 40,4 auf Platz 1: Stechen. Dahinter Gleichstand, der nach Kette getrennt wird,
    # und einer, der bis „mouchen“ gleich bleibt (manuell).
    await api.shoot(setup.tid, starts[1], raw([10.0, 10.0], [10.2, 10.2]))  # 40,4
    # 4 Schuss sind ein Zehnerblock (SpO 0.12.1): gleich bei 39,0, dann trennen die Zehner.
    await api.shoot(setup.tid, starts[2], raw([9.0, 10.0], [10.0, 10.0]))  # 39,0; 3 Zehner
    await api.shoot(setup.tid, starts[3], raw([9.5, 9.5], [10.0, 10.0]))  # 39,0; 2 Zehner
    await api.shoot(setup.tid, starts[4], raw([9.5, 9.5], [10.0, 10.0]))  # wie Start 4

    ranking = await api.ranking(setup.tid, setup.cid)
    rows = {row["start_id"]: row for row in ranking["groups"][0]["rows"]}
    first, second, third, fourth, fifth = (rows[s] for s in starts)
    assert (first["place"], second["place"]) == (1, 1)
    assert first["needs_shootoff"]
    assert second["needs_shootoff"]
    assert first["tie_reason"] == "shootoff"
    assert first["tie_note"] == "Ringgleichheit auf Platz 1: Stechen"
    assert first["score_text"] == "40,4 Ringe"
    assert first["series"][1]["rings"] == "20.1"
    assert third["place"] == 3
    assert not third["tied"]
    assert (fourth["place"], fifth["place"]) == (4, 4)
    assert fourth["tie_reason"] == "manual"
    assert fourth["tie_criterion"] == "mouchen"
    assert fourth["tie_note"].startswith("Ringgleichheit: nach Sportordnung manuell entscheiden")
    assert not fourth["needs_shootoff"]
