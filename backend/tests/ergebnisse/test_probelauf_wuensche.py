"""Wünsche aus dem Probelauf: Vorabauskunft auch für abgebrochene Starts, offene Serien je
Abschnitt, Meldung bei fehlenden Pflichtwerten, Zehner bei Trefferzählung, Kurztext im
Gleichstandshinweis, gemessene Zeit bei „Abbruch durch den Schützen“."""

import uuid
from typing import Any

from sqlalchemy import select

from app.modules.ergebnisse.models import ResultCurrent
from app.modules.ergebnisse.recompute import sync_hits_only_tens
from tests.ergebnisse.conftest import Api, Setup, falls, make_setup, shots
from tests.ergebnisse.test_capture_switch import targets, trap_definition
from tests.ergebnisse.test_starts_hooks import person_start


def serie(seconds: int, standing: int = 0) -> dict[str, Any]:
    return {"time_cs": seconds * 100, "standing": standing}


# --- 1. Vorabauskunft für abgebrochene Starts ------------------------------------------------


async def test_abort_preview_for_aborted_dnf_start(api: Api, fallscheibe: Setup) -> None:
    tid = fallscheibe.tid
    _, sid = await person_start(api, fallscheibe)
    path = api.start_path(tid, sid)
    await api.shoot(tid, sid, falls(serie(15), serie(15)), final=False)
    state = await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dnf"})

    preview = (await api.ok("GET", f"{path}/form"))["abort_preview"]
    assert (preview["would_place"], preview["reason_code"]) == (True, "placed")
    assert preview["score_text"] == "250,00 s"
    assert preview["message_de"] == (
        "Abbruch (AB): kommt nach dem bisherigen Ergebnis in die Rangliste (250,00 s). "
        "Serie 3 und 4 zählen nach der Regel der Wertung."
    )
    # Dieselbe Rechnung wie die Rangliste.
    (row,) = (await api.ranking(tid, fallscheibe.cid))["groups"][0]["rows"]
    assert (row["place"], row["score_text"]) == (1, preview["score_text"])

    # Vorschau einer Korrektur: Serie 3 angefangen, ohne Serienstatus → ohne Platz.
    partial = await api.ok(
        "POST", f"{path}/preview", json={"raw": falls(serie(15), serie(15), {"time_cs": 900})}
    )
    assert partial["abort_preview"]["would_place"] is False
    assert partial["abort_preview"]["reason_code"] == "incomplete_series"
    assert partial["status"] == "aborted"
    assert state["status"] == "aborted"


async def test_abort_preview_dns_dsq_and_final(api: Api, precision: Setup) -> None:
    tid = precision.tid
    expected = [
        ("dns", "not_started", "Nicht angetreten: ohne Platz."),
        ("dsq", "disqualified", "Disqualifiziert: ohne Platz."),
    ]
    for reason, code, message in expected:
        _, sid = await person_start(api, precision)
        path = api.start_path(tid, sid)
        await api.ok("POST", f"{path}/result/abort", json={"abort_reason": reason})
        for preview in (
            (await api.ok("GET", f"{path}/form"))["abort_preview"],
            (await api.ok("POST", f"{path}/preview", json={"raw": shots([10] * 5)}))[
                "abort_preview"
            ],
        ):
            assert preview["would_place"] is False
            assert (preview["reason_code"], preview["message_de"]) == (code, message)
            assert preview["score_text"] is None

    _, sid = await person_start(api, precision)
    await api.shoot(tid, sid, shots([10] * 5, [9] * 5))
    path = api.start_path(tid, sid)
    assert (await api.ok("GET", f"{path}/form"))["abort_preview"] is None
    preview = await api.ok("POST", f"{path}/preview", json={"raw": shots([10] * 5, [8] * 5)})
    assert preview["abort_preview"] is None


# --- 2. Offene Serien je Abschnitt ------------------------------------------------------------


def two_sections() -> dict[str, Any]:
    section = {"serien": 2, "schuss_je_serie": 5}
    return {
        "variant": {
            "id": "standard",
            "name": "Standard",
            "abschnitte": [
                {"id": "liegend", "name": "Liegend", **section},
                {"id": "stehend", "name": "Stehend", **section},
            ],
        },
        "scoring": {"modell": "ringe", "rangfolge": "absteigend", "geprueft": False},
    }


async def test_open_series_items_name_section_and_state(api: Api) -> None:
    setup = await make_setup(api, definition=two_sections(), capture_mode="shot")
    _, sid = await person_start(api, setup)
    raw = {
        "sections": {
            "liegend": {"series": [{"shots": [10] * 5}, {"shots": [9] * 5}]},
            "stehend": {"series": [{"shots": [8, 8]}]},
        }
    }
    preview = await api.ok("POST", f"{api.start_path(setup.tid, sid)}/preview", json={"raw": raw})
    abort = preview["abort_preview"]
    assert abort["open_series"] == [1, 2]
    assert abort["open_series_items"] == [
        {
            "section_id": "stehend",
            "section_name": "Stehend",
            "series": 1,
            "path": "sections.stehend.series[0]",
            "state": "started",
        },
        {
            "section_id": "stehend",
            "section_name": "Stehend",
            "series": 2,
            "path": "sections.stehend.series[1]",
            "state": "not_shot",
        },
    ]
    # Pfade wie in der Maske.
    form = await api.ok("GET", f"{api.start_path(setup.tid, sid)}/form")
    paths = {s["path"] for section in form["form"]["sections"] for s in section["series"]}
    assert {item["path"] for item in abort["open_series_items"]} <= paths


# --- 3. Meldung bei unvollständigen Serien ----------------------------------------------------


async def test_incomplete_series_without_status(api: Api, fallscheibe: Setup) -> None:
    _, sid = await person_start(api, fallscheibe)
    preview = await api.ok(
        "POST",
        f"{api.start_path(fallscheibe.tid, sid)}/preview",
        json={"raw": falls(serie(15), serie(15), {"time_cs": 900})},
    )
    abort = preview["abort_preview"]
    assert abort["reason_code"] == "incomplete_series"
    assert abort["message_de"] == (
        "Serie 3 ist unvollständig erfasst – ohne Serienstatus ‚Abbruch durch den Schützen‘ "
        "bleibt der Start ohne Platz."
    )
    assert abort["missing_fields"] == []
    states = [(i["series"], i["state"]) for i in abort["open_series_items"]]
    assert states == [(3, "started"), (4, "not_shot")]


async def test_status_set_but_values_missing(api: Api, fallscheibe: Setup) -> None:
    _, sid = await person_start(api, fallscheibe)
    preview = await api.ok(
        "POST",
        f"{api.start_path(fallscheibe.tid, sid)}/preview",
        json={"raw": falls(serie(15), serie(15), {"status": "aborted_by_shooter"})},
    )
    abort = preview["abort_preview"]
    assert (abort["would_place"], abort["reason_code"]) == (False, "missing_values")
    assert abort["message_de"] == "Serie 3: Anzahl stehender Scheiben fehlt."
    assert abort["missing_fields"] == [
        {"path": "sections.fallscheibe.series[2]", "key": "standing", "label": "Stehende Scheiben"}
    ]
    # Mit den stehenden Scheiben wäre der Start platzierbar.
    fixed = falls(serie(15), serie(15), {"status": "aborted_by_shooter", "standing": 5})
    preview = await api.ok(
        "POST", f"{api.start_path(fallscheibe.tid, sid)}/preview", json={"raw": fixed}
    )
    assert preview["abort_preview"]["reason_code"] == "placed"
    assert preview["abort_preview"]["missing_fields"] == []


# --- 4. Zehner bei reiner Trefferzählung ------------------------------------------------------


def _with_tens(computed: dict[str, Any]) -> dict[str, Any]:
    """Wie ein Stand älterer Versionen: Zehner 0 statt null."""
    return {
        **computed,
        "tens": 0,
        "inner_tens": 0,
        "sections": [
            {**section, "series": [{**s, "tens": 0, "inner_tens": 0} for s in section["series"]]}
            for section in computed["sections"]
        ],
    }


async def test_hits_only_tens_are_null_on_read_and_synced(api: Api, precision: Setup) -> None:
    setup = await make_setup(api, definition=trap_definition(), capture_mode="shot")
    _, sid = await person_start(api, setup)
    await api.shoot(setup.tid, sid, targets([1, 1, 0, 1, 1], [1] * 5))
    # Ein Ringwettbewerb mit echten Zehnern bleibt unberührt.
    _, ring = await person_start(api, precision)
    await api.shoot(precision.tid, ring, shots([10] * 5, [9] * 5))

    factory = api.app.state.session_factory
    async with factory() as session:
        current = await session.get(ResultCurrent, uuid.UUID(sid))
        assert current is not None
        assert current.computed is not None
        assert current.computed["tens"] is None  # heute schon null
        current.computed = _with_tens(current.computed)
        await session.commit()

    # Beim Lesen: null wie in der Rangliste.
    form = await api.ok("GET", f"{api.start_path(setup.tid, sid)}/form")
    computed = form["current"]["computed"]
    assert (computed["tens"], computed["inner_tens"]) == (None, None)
    assert {s["tens"] for s in computed["sections"][0]["series"]} == {None}
    (row,) = (await api.ranking(setup.tid, setup.cid))["groups"][0]["rows"]
    assert (row["tens"], row["inner_tens"]) == (None, None)

    # Abgleich beim Start: nur der betroffene Wettbewerb, danach nichts mehr zu tun.
    async with factory() as session:
        result = await sync_hits_only_tens(session)
        await session.commit()
    assert result is not None
    assert result.competition_ids == [uuid.UUID(setup.cid)]
    assert result.recomputed == 1
    async with factory() as session:
        stored = {
            row.start_id: row.computed for row in await session.scalars(select(ResultCurrent))
        }
        assert stored[uuid.UUID(sid)]["tens"] is None
        assert stored[uuid.UUID(sid)]["sections"][0]["series"][0]["tens"] is None
        assert stored[uuid.UUID(ring)]["tens"] == 5
        assert await sync_hits_only_tens(session) is None
    audit = (await api.ok("GET", "/audit", params={"limit": 50}))["items"]
    triggers = [i["details"].get("trigger") for i in audit if i["action"] == "result.recomputed"]
    assert triggers == ["hits_only_tens"]


# --- 5. Gleichstandshinweis: Kurz- und Langtext -----------------------------------------------


def ten_shot_definition() -> dict[str, Any]:
    return {
        "variant": {
            "id": "standard",
            "name": "Standard",
            "abschnitte": [
                {"id": "praezision", "name": "Präzision", "serien": 2, "schuss_je_serie": 10}
            ],
        },
        "scoring": {
            "modell": "ringe",
            "rangfolge": "absteigend",
            "gleichstand": ["letzte_serie_rueckwaerts"],
            "geprueft": False,
        },
    }


async def test_tie_note_short_and_long(api: Api) -> None:
    setup = await make_setup(api, definition=ten_shot_definition(), capture_mode="shot")
    _, a = await person_start(api, setup)
    _, b = await person_start(api, setup)
    await api.shoot(setup.tid, a, shots([9] * 10, [10] * 10))  # 190, letzte Serie 100
    await api.shoot(setup.tid, b, shots([10] * 10, [9] * 10))  # 190, letzte Serie 90
    rows = (await api.ranking(setup.tid, setup.cid))["groups"][0]["rows"]
    assert [(r["start_id"], r["place"]) for r in rows] == [(a, 1), (b, 2)]
    for row in rows:
        assert row["tie_reason"] == "resolved"
        assert row["tie_note"] == "Ringgleichheit, entschieden nach: letzte Zehnerserie"
        assert row["tie_note_long"] == (
            "Ringgleichheit, entschieden nach: letzte Zehnerserie, dann rückwärts in "
            "10-Schuss-Serien (Wurfscheibe: je Serie)"
        )


async def test_tie_note_short_text_for_hits_only(api: Api) -> None:
    definition = trap_definition()
    definition["scoring"]["gleichstand"] = ["letzte_serie_rueckwaerts"]
    setup = await make_setup(api, definition=definition, capture_mode="shot")
    _, a = await person_start(api, setup)
    _, b = await person_start(api, setup)
    await api.shoot(setup.tid, a, targets([1, 1, 1, 0, 0], [1] * 5))  # 8, letzte Serie 5
    await api.shoot(setup.tid, b, targets([1] * 5, [1, 1, 1, 0, 0]))  # 8, letzte Serie 3
    rows = (await api.ranking(setup.tid, setup.cid))["groups"][0]["rows"]
    assert [r["start_id"] for r in rows] == [a, b]
    assert rows[0]["tie_note"] == "Treffergleichheit, entschieden nach: letzte Serie"
    assert rows[0]["tie_note_long"].startswith(
        "Treffergleichheit, entschieden nach: letzte Zehnerserie, dann"
    )


# --- 6. Gemessene Zeit bei „Abbruch durch den Schützen“ ----------------------------------------


async def test_measured_time_is_kept_but_not_scored(api: Api, fallscheibe: Setup) -> None:
    tid = fallscheibe.tid
    _, sid = await person_start(api, fallscheibe)
    path = api.start_path(tid, sid)
    form = await api.ok("GET", f"{path}/form")
    status = next(
        field
        for field in form["form"]["sections"][0]["series"][0]["fields"]
        if field["key"] == "status"
    )
    options = {option["key"]: option for option in status["options"]}
    assert options["aborted_by_shooter"]["required_fields"] == ["standing"]
    assert options["aborted_by_shooter"]["unscored_fields"] == ["time_cs"]
    assert options["time_limit"]["unscored_fields"] == ["time_cs"]
    assert options["normal"]["unscored_fields"] == []

    aborted = {"status": "aborted_by_shooter", "time_cs": 700, "standing": 2}
    raw = falls(serie(15), aborted)
    state = await api.shoot(tid, sid, raw, final=False)
    assert state["raw"] == raw  # nichts verworfen
    series = state["computed"]["sections"][0]["series"][1]
    assert (series["measured_time_cs"], series["time_cs"]) == (700, 6000)
    assert any("gemessene Zeit 7,00 s wird nicht gewertet" in s for s in state["computed"]["steps"])

    # Auch als Korrektur eines abgebrochenen Starts bleibt der Wert stehen.
    state = await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dnf"})
    corrected = falls(serie(15), {**aborted, "time_cs": 650})
    state = await api.ok(
        "POST",
        f"{path}/correct",
        json={"raw": corrected, "reason": "Zeit nachgetragen", "base_seq": state["seq"]},
    )
    assert state["raw"] == corrected
    events = await api.ok("GET", f"{path}/events")
    changes = [(c["path"], c["before"], c["after"]) for c in events[-1]["changes"]]
    assert changes == [("sections.fallscheibe.series[1].time_cs", 700, 650)]
