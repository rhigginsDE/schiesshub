"""Serienstatus über die API: Erfasstes verschwindet nie.

Für jede Status-Option wird ein Rohwert-Satz mit allen Feldern der Serie gespeichert und wieder
gelesen; danach wechselt der Status zu jedem anderen und zurück. Kein Schlüssel geht verloren,
gewertet wird nur, was der jeweilige Status vorsieht. Dazu die Vorabauskunft, wenn mehreren
Serien Pflichtwerte fehlen.
"""

from typing import Any

import pytest

from tests.ergebnisse.conftest import Api, Setup, falls, make_setup, precision_definition
from tests.ergebnisse.test_starts_hooks import person_start

# Werte, die bei jedem Status der jeweiligen Disziplin gültig sind (Speed: 4 von 5 Schuss,
# damit auch „nicht beendet“ passt).
SETUPS: dict[str, dict[str, Any]] = {
    "fallscheibe": {
        "competition": {"catalog_federation": "bds", "catalog_code": "4401"},
        "values": {"time_cs": 1500, "standing": 2},
    },
    "speed": {
        "competition": {"catalog_federation": "bds", "catalog_code": "1401"},
        "values": {"shots": [10, 7, 10, 0], "sum": 27, "time_cs": 4512},
    },
    "praezision": {
        "competition": {"definition": precision_definition()},
        "values": {"shots": [10, "X", 9, 8, 7], "sum": 45, "tens": 1, "inner_tens": 1},
    },
}

CASES = [
    ("fallscheibe", "series", "normal"),
    ("fallscheibe", "series", "time_limit"),
    ("fallscheibe", "series", "aborted_by_shooter"),
    ("fallscheibe", "series", "malfunction_before_first_shot"),
    ("speed", "shot", "normal"),
    ("speed", "shot", "unfinished"),
    ("speed", "series", "normal"),
    ("speed", "series", "unfinished"),
    ("praezision", "series", "normal"),
    ("praezision", "shot", "normal"),
]


def _status_keys(series: dict[str, Any]) -> list[str]:
    status = next((f for f in series["fields"] if f["key"] == "status"), None)
    return [o["key"] for o in status["options"]] if status else ["normal"]


def _raw(section: str, values: dict[str, Any], status: str) -> dict[str, Any]:
    series = dict(values) if status == "normal" else {"status": status, **values}
    return {"sections": {section: {"series": [series]}}}


@pytest.mark.parametrize(("name", "mode", "status"), CASES)
async def test_all_fields_survive_every_status(api: Api, name: str, mode: str, status: str) -> None:
    config = SETUPS[name]
    setup: Setup = await make_setup(api, capture_mode=mode, **config["competition"])
    _, sid = await person_start(api, setup)
    path = api.start_path(setup.tid, sid)
    form = (await api.ok("GET", f"{path}/form"))["form"]
    section = form["sections"][0]
    series = section["series"][0]
    keys = [f["key"] for f in series["fields"] if f["key"] != "status"]
    values = {key: config["values"][key] for key in keys}  # alle Felder der Maske
    statuses = _status_keys(series)
    assert status in statuses

    raw = _raw(section["id"], values, status)
    state = await api.put_raw(setup.tid, sid, raw, 0)
    assert state["raw"] == raw
    read = (await api.ok("GET", f"{path}/form"))["current"]
    assert read["raw"] == raw
    assert read["computed"]["sections"][0]["series"][0]["status"] == status

    # Status hin und zurück: nichts geht verloren.
    seq = state["seq"]
    for other in [s for s in statuses if s != status] + [status]:
        changed = _raw(section["id"], values, other)
        state = await api.put_raw(setup.tid, sid, changed, seq)
        seq = state["seq"]
        assert state["raw"] == changed, other
        assert state["computed"]["sections"][0]["series"][0]["status"] == other
    assert state["raw"] == raw
    final = (await api.ok("GET", f"{path}/form"))["current"]
    assert final["raw"] == raw


async def test_abort_preview_names_all_missing_fields(api: Api) -> None:
    config = SETUPS["fallscheibe"]
    setup = await make_setup(api, capture_mode="series", **config["competition"])
    _, sid = await person_start(api, setup)
    raw = falls(
        {"time_cs": 1500, "standing": 0},
        {"status": "aborted_by_shooter"},
        {"status": "time_limit", "time_cs": 6100},
    )
    preview = await api.ok("POST", f"{api.start_path(setup.tid, sid)}/preview", json={"raw": raw})
    abort = preview["abort_preview"]
    assert abort["reason_code"] == "missing_values"
    assert abort["message_de"] == (
        "Es fehlen noch: Serie 2 (Stehende Scheiben) und Serie 3 (Stehende Scheiben). Ohne "
        "diese Werte bleibt der Start ohne Platz."
    )
    assert [(f["path"], f["key"]) for f in abort["missing_fields"]] == [
        ("sections.fallscheibe.series[1]", "standing"),
        ("sections.fallscheibe.series[2]", "standing"),
    ]
