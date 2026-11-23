"""Bemerkung zum Abbruch (`abort_note`) in Startliste, Reihenfolge und „am Schießstand“.

Nur für die Bedienung (`names=full`), nie in den öffentlichen Sichten.
"""

from app.modules.starts import hooks
from tests.starts.conftest import Api, Setup


async def _aborted_with_note(api: Api, setup: Setup, note: str | None) -> str:
    entry = await api.entry(setup.tid, setup.class_id)
    (start,) = await api.book(setup.tid, entry["id"], setup.competition_id)
    body = {"abort_reason": "dnf"} | ({"note": note} if note else {})
    await api.ok("POST", f"/tournaments/{setup.tid}/starts/{start['id']}/abort", json=body)
    return start["id"]


async def test_abort_note_only_with_full_names(api: Api, queue_setup: Setup) -> None:
    setup = queue_setup
    await api.set_status(setup.tid, "active")
    noted = await _aborted_with_note(api, setup, "Waffenstörung, aufgegeben")
    plain = await _aborted_with_note(api, setup, None)
    path = f"/tournaments/{setup.tid}/startlist"

    full = {row["start_id"]: row for row in await api.ok("GET", path, params={"names": "full"})}
    public = {row["start_id"]: row for row in await api.ok("GET", path)}

    assert full[noted]["abort_note"] == "Waffenstörung, aufgegeben"
    assert full[plain]["abort_note"] is None
    assert public[noted]["abort_note"] is None
    assert "Waffenstörung" not in str(public)


async def test_lane_views_carry_the_field(api: Api, queue_setup: Setup) -> None:
    """Ein Abbruch gibt den Schützenstand frei; Reihenfolge und „am Schießstand“ führen das Feld
    trotzdem (gleiches Format wie die Startliste), dort ist es leer."""
    setup = queue_setup
    await api.set_status(setup.tid, "active")
    await _aborted_with_note(api, setup, "Unwohl")
    entry = await api.entry(setup.tid, setup.class_id)
    (start,) = await api.book(setup.tid, entry["id"], setup.competition_id)
    await api.ok("POST", f"/tournaments/{setup.tid}/starts/{start['id']}/call")

    for view in ("queue", "now"):
        body = await api.ok(
            "GET",
            f"/tournaments/{setup.tid}/ranges/{setup.range_id}/{view}",
            params={"names": "full"},
        )
        on_lane = [lane["start"] for lane in body["lanes"] if lane["start"] is not None]
        assert [(row["start_id"], row["abort_note"]) for row in on_lane] == [(start["id"], None)], (
            view
        )
        assert "Unwohl" not in str(body)


async def test_abort_note_provider_hook_takes_precedence(api: Api, queue_setup: Setup) -> None:
    setup = queue_setup
    await api.set_status(setup.tid, "active")
    noted = await _aborted_with_note(api, setup, "aus dem Protokoll")

    async def provider(session, start_ids):
        return dict.fromkeys(start_ids, "vom Modul")

    hooks.register_abort_note_provider(provider)
    try:
        rows = await api.ok("GET", f"/tournaments/{setup.tid}/startlist", params={"names": "full"})
    finally:
        hooks.unregister_abort_note_provider(provider)
    assert {row["start_id"]: row["abort_note"] for row in rows}[noted] == "vom Modul"
