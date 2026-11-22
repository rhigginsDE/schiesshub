"""Anmeldestellen `starts.hooks`: Ergebnisprüfer und Abbruch-Handler, ohne das Ergebnis-Modul."""

import uuid
from collections.abc import Iterator, Sequence

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventHub
from app.core.security import Actor
from app.modules.starts import hooks
from app.modules.starts.rules import AbortReason
from tests.starts.conftest import Api, Setup


@pytest.fixture
def without_abort_handler(api: Api) -> Iterator[None]:
    """Wie ohne Ergebnis-Modul: kein Abbruch-Handler angemeldet."""
    handler = hooks.abort_handler()
    if handler is not None:
        hooks.unregister_abort_handler(handler)
    yield
    if handler is not None:
        hooks.register_abort_handler(handler)


async def test_abort_without_handler_only_changes_status(
    api: Api, queue_setup: Setup, without_abort_handler: None
) -> None:
    tid = queue_setup.tid
    entry = await api.entry(tid, queue_setup.class_id)
    start = (await api.book(tid, entry["id"], queue_setup.competition_id))[0]
    aborted = await api.ok(
        "POST", f"/tournaments/{tid}/starts/{start['id']}/abort", json={"abort_reason": "dns"}
    )
    assert (aborted["status"], aborted["abort_reason"]) == ("aborted", "dns")
    names = [event.name for event in api.drain()]
    assert "start.status_changed" in names
    assert "result.aborted" not in names
    # Ohne Ereignis im Protokoll lässt sich die Anmeldung mit dem DNS-Start löschen.
    await api.ok("DELETE", f"/tournaments/{tid}/entries/{entry['id']}", 204)


async def test_abort_handler_takes_over(
    api: Api, queue_setup: Setup, without_abort_handler: None
) -> None:
    calls: list[tuple[uuid.UUID, uuid.UUID, str, str | None]] = []

    async def handler(
        session: AsyncSession,
        events: EventHub,
        actor: Actor,
        tournament_id: uuid.UUID,
        start_id: uuid.UUID,
        abort_reason: AbortReason,
        note: str | None,
    ) -> None:
        calls.append((tournament_id, start_id, abort_reason, note))

    hooks.register_abort_handler(handler)
    try:
        tid = queue_setup.tid
        entry = await api.entry(tid, queue_setup.class_id)
        start = (await api.book(tid, entry["id"], queue_setup.competition_id))[0]
        result = await api.ok(
            "POST",
            f"/tournaments/{tid}/starts/{start['id']}/abort",
            json={"abort_reason": "dnf", "note": "Waffenstörung"},
        )
        # Der Handler hat nichts geändert; die Antwort zeigt den Stand danach.
        assert result["status"] == "registered"
        assert calls == [(uuid.UUID(tid), uuid.UUID(start["id"]), "dnf", "Waffenstörung")]
        # Unbekannter Start: 404, bevor der Handler gefragt wird.
        await api.fail(
            "POST",
            f"/tournaments/{tid}/starts/{uuid.uuid4()}/abort",
            404,
            json={"abort_reason": "dns"},
        )
        assert len(calls) == 1
    finally:
        hooks.unregister_abort_handler(handler)


async def test_result_check_blocks_delete_and_cancel(api: Api, queue_setup: Setup) -> None:
    tid = queue_setup.tid
    entry = await api.entry(tid, queue_setup.class_id)
    start = (await api.book(tid, entry["id"], queue_setup.competition_id))[0]
    marked = {uuid.UUID(start["id"])}

    async def check(session: AsyncSession, start_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        return marked & set(start_ids)

    hooks.register_result_check(check)
    try:
        detail = await api.fail("DELETE", f"/tournaments/{tid}/entries/{entry['id']}", 409)
        assert detail == (
            "Zu Starts dieser Anmeldung gibt es Einträge im Ergebnisprotokoll (zum Beispiel "
            "„nicht angetreten“). Die Anmeldung lässt sich deshalb nicht löschen."
        )
        detail = await api.fail("DELETE", f"/tournaments/{tid}/starts/{start['id']}", 409)
        assert "Ergebnisprotokoll" in detail
    finally:
        hooks.unregister_result_check(check)
    await api.ok("DELETE", f"/tournaments/{tid}/starts/{start['id']}", 204)
    await api.ok("DELETE", f"/tournaments/{tid}/entries/{entry['id']}", 204)
