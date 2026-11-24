"""Wechsel der Erfassungsart: Seriensumme aus Einzelwerten (Ringe und je Ziel) und Felder im
Verlauf mit deutschem Namen."""

from typing import Any

from tests.ergebnisse.conftest import Api, make_setup, shots
from tests.ergebnisse.test_starts_hooks import person_start


def trap_definition() -> dict[str, Any]:
    """Wurfscheibe: 2 Serien zu 5 Zielen, Treffer 1/0 je Ziel."""
    return {
        "variant": {
            "id": "standard",
            "name": "Standard",
            "abschnitte": [
                {
                    "id": "trap",
                    "name": "Trap",
                    "serien": 2,
                    "ziele_je_serie": 5,
                    "max_schuss_je_serie": 10,
                    "ringwerte": [1, 0],
                }
            ],
        },
        "scoring": {"modell": "ringe", "rangfolge": "absteigend", "geprueft": False},
    }


def targets(*series: list[int]) -> dict[str, Any]:
    return {"sections": {"trap": {"series": [{"shots": list(s)} for s in series]}}}


async def test_per_target_values_appear_as_series_sum(api: Api) -> None:
    setup = await make_setup(api, definition=trap_definition(), capture_mode="shot")
    _, sid = await person_start(api, setup)
    path = api.start_path(setup.tid, sid)
    await api.shoot(setup.tid, sid, targets([1, 1, 0, 1, 1]), final=False)

    shot_form = await api.ok("GET", f"{path}/form", params={"capture_mode": "shot"})
    assert shot_form["derived_values"] == []
    series_form = await api.ok("GET", f"{path}/form", params={"capture_mode": "series"})
    assert series_form["derived_values"] == [
        {"path": "sections.trap.series[0]", "key": "sum", "value": 4, "source": "shots"}
    ]
    # Nichts gespeichert: weiterhin ein Ereignis, Rohwerte unverändert.
    assert series_form["current"]["seq"] == 1
    assert series_form["current"]["raw"] == targets([1, 1, 0, 1, 1])
    hints = series_form["form"]["sections"][0]["series"][0]["hints"]
    assert "5 Ziele" in hints

    # Verlauf: Felder mit deutschem Namen, nicht „shots“.
    state = await api.put_raw(setup.tid, sid, targets([1, 1, 0, 1, 1], [1, 0]), 1)
    await api.put_raw(
        setup.tid,
        sid,
        {"sections": {"trap": {"series": [{"sum": 4}, {"shots": [1, 0]}]}}},
        state["seq"],
    )
    events = await api.ok("GET", f"{path}/events")
    labels = [[c["label"] for c in e["changes"]] for e in events]
    assert labels[0] == ["Serie 1 · Treffer je Ziel"]
    assert labels[1] == ["Serie 2 · Treffer je Ziel"]
    assert labels[2] == ["Serie 1 · Treffer je Ziel", "Serie 1 · Treffer"]


async def test_ring_shots_appear_as_series_sum_with_tens(api: Api) -> None:
    definition = {
        "variant": {
            "id": "standard",
            "name": "Standard",
            "abschnitte": [
                {"id": "praezision", "name": "Präzision", "serien": 2, "schuss_je_serie": 5}
            ],
        },
        "scoring": {
            "modell": "ringe",
            "rangfolge": "absteigend",
            "gleichstand": ["zehner", "innenzehner"],
            "geprueft": False,
        },
    }
    setup = await make_setup(api, definition=definition, capture_mode="shot")
    _, sid = await person_start(api, setup)
    await api.shoot(setup.tid, sid, shots([10, "X", 9, 9, 8]), final=False)
    form = await api.ok(
        "GET", f"{api.start_path(setup.tid, sid)}/form", params={"capture_mode": "series"}
    )
    values = {item["key"]: item["value"] for item in form["derived_values"]}
    assert values == {"sum": 46, "tens": 2, "inner_tens": 1}
    assert {item["path"] for item in form["derived_values"]} == {"sections.praezision.series[0]"}
    assert all(item["kind"] for item in form["form"]["note_items"])
    events = await api.ok("GET", f"{api.start_path(setup.tid, sid)}/events")
    assert events[0]["changes"][0]["label"] == "Serie 1 · Schüsse"
