"""Geführte Wiederherstellung über die API: Quellen, Vorschau, Ausführung, Wartung, Fehlerfälle.

Die Tests tauschen die Testdatenbank wirklich aus (ALTER DATABASE … RENAME). Danach heißt die
neue Datenbank wieder wie die Testdatenbank; die alte (`…_pre_restore_…`) wird am Ende gelöscht.
"""

import asyncio
import os
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.modules.backup import guided, maintenance
from tests.backup.conftest import PASSPHRASE, BackupApp
from tests.conftest import BACKEND_DIR
from tests.ergebnisse.conftest import Api, Setup, make_setup, precision_definition, shots

API = "/api/v1"
FULL = shots([10] * 5, [9] * 5)
PARTIAL = shots([10] * 5)


def _api(backup: BackupApp) -> Api:
    return Api(
        client=backup.client,
        app=backup.app,
        events=backup.app.state.events.subscribe(),
        data_dir=backup.env.data_dir,
    )


async def _start(api: Api, setup: Setup, name: str) -> str:
    eid = await api.entry(setup.tid, setup.class_id, name=name)
    return (await api.starts(setup.tid, eid, setup.cid))[0]


async def _restore_databases(url: str) -> list[str]:
    """Neue (`<name>_restore_…`) und alte (`<name>_pre_restore_…`) Datenbanken dieses Laufs.

    Genau nach Präfix, nicht per LIKE: Dort ist `_` ein Platzhalter, und ein paralleler Lauf
    (`…_restore2_…`) würde mitgezählt und mitgelöscht.
    """
    name = make_url(url).database
    prefixes = (f"{name}_restore_", f"{name}_pre_restore_")
    admin = create_async_engine(make_url(url).set(database="postgres"))
    try:
        async with admin.connect() as connection:
            rows = await connection.scalars(text("SELECT datname FROM pg_database ORDER BY 1"))
            return [row for row in rows if row.startswith(prefixes)]
    finally:
        await admin.dispose()


async def _drop(url: str, names: list[str]) -> None:
    admin = create_async_engine(
        make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as connection:
        for name in names:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


@pytest.fixture
async def leftovers(test_database_url: str, engine: AsyncEngine) -> AsyncIterator[None]:
    """Räumt alte und halbfertige Datenbanken weg; der Pool der Tests ist danach neu."""
    yield
    await engine.dispose()
    await _drop(test_database_url, await _restore_databases(test_database_url))


async def _wait(client: httpx.AsyncClient, timeout_s: float = 120) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        response = await client.get(f"{API}/backup/restore/status")
        if response.status_code == 200 and response.json()["state"] in ("succeeded", "failed"):
            return response.json()
        assert response.status_code in (200, 503), response.text
        await asyncio.sleep(0.1)
    raise AssertionError("Die Wiederherstellung ist nicht fertig geworden.")


async def _snapshot_to_usb(backup: BackupApp) -> str:
    await backup.client.put(f"{API}/backup/passphrase", json={"passphrase": PASSPHRASE})
    backup.env.plug_in()
    await backup.client.post(f"{API}/backup/usb/recheck")
    _local, usb_run = (await backup.client.post(f"{API}/backup/run")).json()
    assert usb_run["ok"], usb_run
    return f"usb:{usb_run['file_name']}"


async def _results(engine: AsyncEngine) -> dict[str, Any]:
    async with engine.connect() as connection:
        events = (
            await connection.execute(
                text("SELECT id, start_id, seq, type FROM result_event ORDER BY start_id, seq")
            )
        ).all()
        current = (
            await connection.execute(
                text("SELECT start_id, score, is_final, last_seq FROM result_current ORDER BY 1")
            )
        ).all()
        starts = (await connection.execute(text("SELECT id, status FROM start ORDER BY id"))).all()
    return {"events": events, "current": current, "starts": starts}


def _broken_copy(path: Path) -> Path:
    """Kopie mit einem gekippten Byte mitten im verschlüsselten Strom."""
    broken = path.with_name("snapshot-20260101T000000Z.shb")
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    broken.write_bytes(bytes(data))
    # Prüfsumme der unversehrten Datei daneben, wie nach einem Lesefehler des Sticks.
    Path(f"{broken}.sha256").write_bytes(Path(f"{path}.sha256").read_bytes())
    return broken


# --- Bausteine ------------------------------------------------------------------------


def test_schema_check_states() -> None:
    _known, heads = guided._revisions()
    assert guided.schema_check(list(heads)).state == "same"
    assert guided.schema_check(["0015_auth_rechte"]).state == "older"
    newer = guided.schema_check(["9999_zukunft"])
    assert newer.state == "newer"
    assert "neueren Version" in newer.message_de
    assert guided.schema_check([]).state == "newer"
    # Maßstab ist die laufende Datenbank, nicht die (vielleicht neueren) Migrationsdateien.
    old = ["0015_auth_rechte"]
    assert guided.schema_check(old, current=old).state == "same"
    assert guided.schema_check(list(heads), current=old).state == "newer"
    assert guided.schema_check(["0014_politur"], current=old).state == "older"


def test_copy_text_parsing() -> None:
    from app.modules.backup import dumpinfo

    parsed = dumpinfo.parse_copy(
        "COPY public.tournament (id, name, status) FROM stdin;\n"
        "a1\tVereins\\tpokal \\\\ Süd\t\\N\n"
        "\\.\n"
    )
    assert parsed["tournament"] == [{"id": "a1", "name": "Vereins\tpokal \\ Süd", "status": None}]


def test_key_plan(tmp_path: Path) -> None:
    from app.core import crypto as field_crypto

    server = tmp_path / "server"
    backup = tmp_path / "backup"
    field_crypto.load_keyring(server, create=True)
    field_crypto.load_keyring(backup, create=True)
    (backup / "backup-key.json").write_text("{}", encoding="utf-8")
    (server / "backup-key.json").write_text('{"neu": 1}', encoding="utf-8")
    assert guided.plan_keys(backup, server, live_persons=3).conflicts == ["field-keys.json"]
    unused = guided.plan_keys(backup, server, live_persons=0)
    assert (unused.field_keys, unused.backup_key) == ("replace_unused", "keep_current")
    assert unused.install == ["field-keys.json"]
    # Schlüsselwechsel nach der Sicherung: Der Server kennt den alten Schlüssel noch.
    field_crypto.rotate_key(backup)
    (server / "field-keys.json").write_bytes((backup / "field-keys.json").read_bytes())
    field_crypto.rotate_key(server)
    backup_only_old = tmp_path / "alt"
    backup_only_old.mkdir()
    (backup_only_old / "field-keys.json").write_bytes((backup / "field-keys.json").read_bytes())
    assert guided.plan_keys(backup_only_old, server, live_persons=3).field_keys == "compatible"
    assert guided.plan_keys(None, server, live_persons=3).field_keys == "none"


# --- Wartungszustand ------------------------------------------------------------------


async def test_maintenance_blocks_writes_then_everything(backup: BackupApp) -> None:
    state: maintenance.MaintenanceState = backup.app.state.maintenance
    queue = backup.app.state.events.subscribe()
    state.begin()
    try:
        write = await backup.client.post(
            f"{API}/tournaments", json={"name": "Gesperrt", "date_from": "2027-01-01"}
        )
        read = await backup.client.get(f"{API}/backup/maintenance")
        state.set_exclusive(True)
        blocked_read = await backup.client.get(f"{API}/tournaments")
    finally:
        state.end()
    after = await backup.client.get(f"{API}/tournaments")

    assert write.status_code == 503
    assert write.json()["code"] == "maintenance"
    assert write.headers["retry-after"]
    assert read.status_code == 200
    assert read.json()["active"] is True
    assert blocked_read.status_code == 503
    assert after.status_code == 200
    names = [queue.get_nowait().name for _ in range(queue.qsize())]
    assert names.count(maintenance.EVENT_MAINTENANCE) == 3


async def test_maintenance_ends_only_when_database_answers(
    backup: BackupApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nach dem Tausch: Probeabfrage über den Pool der App, wiederholt, bis sie gelingt."""
    manager: guided.RestoreManager = backup.app.state.backup_restore
    real = backup.app.state.session_factory
    calls: list[int] = []

    def flaky() -> Any:
        calls.append(1)
        if len(calls) < 3:
            raise OSError("Datenbank startet noch")
        return real()

    def app_with(factory: Any) -> SimpleNamespace:
        return SimpleNamespace(state=SimpleNamespace(session_factory=factory))

    def down() -> Any:
        raise OSError("Datenbank weg")

    monkeypatch.setattr(manager, "app", app_with(flaky))
    monkeypatch.setattr(guided, "READY_INTERVAL_S", 0.01)
    assert await manager._wait_until_ready() is True
    assert len(calls) == 3

    monkeypatch.setattr(guided, "READY_TIMEOUT_S", 0.05)
    monkeypatch.setattr(manager, "app", app_with(down))
    assert await manager._wait_until_ready() is False


async def test_gate_wraps_an_already_built_stack(backup_settings: Any, clean_db: None) -> None:
    """Unter Uvicorn steht der Schichtenstapel schon, bevor die Module starten."""
    from app.main import create_app
    from tests.conftest import running

    app = create_app(backup_settings)
    app.middleware_stack = app.build_middleware_stack()
    async with running(app) as client:
        app.state.maintenance.begin()
        try:
            response = await client.post(f"{API}/backup/run")
        finally:
            app.state.maintenance.end()
    assert response.status_code == 503


# --- Ganzer Ablauf --------------------------------------------------------------------


async def test_restore_round_trip(
    backup: BackupApp,
    engine: AsyncEngine,
    test_database_url: str,
    leftovers: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api(backup)
    manager = backup.app.state.backup_restore
    probe = manager._wait_until_ready
    probes: list[bool] = []

    async def recording_probe() -> bool:
        probes.append(backup.app.state.maintenance.active)
        return await probe()

    monkeypatch.setattr(manager, "_wait_until_ready", recording_probe)
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    a = await _start(api, setup, "Alma Vorher")
    b = await _start(api, setup, "Bert Halb")
    await api.shoot(setup.tid, a, FULL)  # seq 1, 2
    await api.shoot(setup.tid, b, PARTIAL, final=False)  # seq 1
    source_id = await _snapshot_to_usb(backup)
    in_backup = await _results(engine)

    # Nach der Sicherung: B fertig (2 Ereignisse aus der Mitschrift), neuer Start E (fehlt).
    state = await api.put_raw(setup.tid, b, FULL, 1)
    await api.finalize(setup.tid, b, state["seq"])
    e = await _start(api, setup, "Emil Neu")
    await api.shoot(setup.tid, e, FULL)
    before = await _results(engine)

    sources = (await backup.client.get(f"{API}/backup/restore/sources")).json()
    listed = {item["id"]: item for item in sources["sources"]}
    assert listed[source_id]["needs_passphrase"] is True
    assert listed[source_id]["checksum_present"] is True
    assert listed[source_id]["journal_available"] is True
    # Dieselbe Sicherung auf Stick und Server: ein Eintrag, der Stick zuerst (mit Schlüsseln).
    local_id = "local:" + source_id.split(":", 1)[1].removesuffix(".shb") + ".dump"
    assert listed[source_id]["locations"] == ["usb", "local"]
    assert listed[source_id]["other_ids"] == [local_id]
    assert local_id not in listed
    stems = [item["file_name"].rsplit(".", 1)[0] for item in sources["sources"]]
    assert len(stems) == len(set(stems))

    wrong = await backup.client.post(
        f"{API}/backup/restore/preview",
        json={"source_id": source_id, "passphrase": "falsches Passwort hier"},
    )
    assert wrong.status_code == 400
    assert "falsch" in wrong.json()["detail"]
    missing = await backup.client.post(
        f"{API}/backup/restore/preview", json={"source_id": "usb:snapshot-1.shb"}
    )
    assert missing.status_code == 404

    preview = (
        await backup.client.post(
            f"{API}/backup/restore/preview",
            json={"source_id": source_id, "passphrase": PASSPHRASE},
        )
    ).json()
    assert preview["restorable"] is True, preview["problems"]
    assert preview["schema_check"]["state"] == "same", preview["schema_check"]
    assert preview["keys"]["field_keys"] == "same"
    (tournament,) = preview["tournaments"]
    assert tournament["name"] == "Vereinspokal"
    assert (tournament["starts"], tournament["final_results"]) == (2, 1)
    comparison = preview["comparison"]
    assert comparison["events_since_backup"] == 4, comparison
    assert comparison["events_from_journal"] == 2
    assert comparison["events_lost"] == 2
    assert comparison["lost_start_missing"] == 2
    assert comparison["starts_since_backup"] == 1
    assert "4 Ergebnis-Einträge hinzugekommen" in comparison["summary_de"]
    assert "Mitschrift" not in comparison["summary_de"]
    assert preview["access"]["lockout_risk"] is False, preview["access"]
    assert [r["code"] for r in preview["access"]["reasons"]] == ["enforcement_off"]
    assert preview["problem_items"] == []
    assert preview["notes"] == [item["message_de"] for item in preview["note_items"]]
    # Die Kopie auf dem Server lässt sich ebenso ansehen (ohne Passwort, ohne Schlüssel).
    local_preview = (
        await backup.client.post(f"{API}/backup/restore/preview", json={"source_id": local_id})
    ).json()
    assert [n["code"] for n in local_preview["note_items"]] == ["server_copy_without_keys"]
    assert local_preview["source"]["locations"] == ["local"]

    unconfirmed = await backup.client.post(
        f"{API}/backup/restore/execute",
        json={"source_id": source_id, "passphrase": PASSPHRASE, "confirm": "ja"},
    )
    assert unconfirmed.status_code == 400

    started = await backup.client.post(
        f"{API}/backup/restore/execute",
        json={"source_id": source_id, "passphrase": PASSPHRASE, "confirm": preview["confirm"]},
    )
    assert started.status_code == 202, started.text
    second = await backup.client.post(
        f"{API}/backup/restore/execute",
        json={"source_id": source_id, "passphrase": PASSPHRASE, "confirm": source_id},
    )
    assert second.status_code == 409
    status = await _wait(backup.client)
    assert status["state"] == "succeeded", status
    assert [step["state"] for step in status["steps"]] == [
        "done",
        "done",
        "done",
        "done",
        "skipped",
        "done",
        "done",
        "done",
        "done",
    ], status["steps"]
    result = status["result"]
    assert result["journal"]["applied"] == 2
    assert result["journal"]["missing_events"] == 2
    assert result["journal"]["lines"][0].startswith("2 Ereignisse nachgetragen")
    # E wurde nach der Sicherung gebucht: als Liste mit Wettbewerb und Startnummer.
    (skipped,) = result["skipped_starts"]
    assert skipped["reason_code"] == "start_not_in_backup"
    competition = await api.ok("GET", f"/tournaments/{setup.tid}/competitions/{setup.cid}")
    assert skipped["competition_name"] == competition["name"]
    assert skipped["start_number"] is not None
    assert result["journal"]["skipped_starts"] == result["skipped_starts"]
    journal_step = next(step for step in status["steps"] if step["key"] == "journal")
    assert "Mitschrift" not in journal_step["label_de"] + (journal_step["detail_de"] or "")
    assert result["previous_database"].startswith(make_url(test_database_url).database)
    assert result["pre_restore_backup"].startswith("pre-restore/")
    assert result["after_backup_ok"] is True
    assert status["maintenance"] is False
    # Die Wartung endete erst nach der Probeabfrage gegen die neue Datenbank.
    assert probes == [True]

    await engine.dispose()
    after = await _results(engine)
    # A und B wie vor der Wiederherstellung, E fehlt.
    keep = {uuid.UUID(a), uuid.UUID(b)}
    assert [row for row in after["events"] if row.start_id in keep] == [
        row for row in before["events"] if row.start_id in keep
    ]
    assert [row for row in after["current"] if row.start_id in keep] == [
        row for row in before["current"] if row.start_id in keep
    ]
    assert {row.id for row in after["starts"]} == {row.id for row in in_backup["starts"]}
    # Die alte Datenbank ist noch da und enthält E.
    old_url = make_url(test_database_url).set(database=result["previous_database"])
    old = create_async_engine(old_url)
    try:
        assert await _results(old) == before
    finally:
        await old.dispose()
    # Die App läuft weiter: lesen, schreiben, Namen lesbar, Protokoll.
    persons = (await backup.client.get(f"{API}/persons")).json()
    names = {person["name"] for person in persons}
    assert {"Alma Vorher", "Bert Halb"} <= names
    assert "Emil Neu" not in names
    await api.ok("POST", "/tournaments", 201, json={"name": "Danach", "date_from": "2027-05-01"})
    async with engine.connect() as connection:
        audit = await connection.scalar(
            text("SELECT details FROM audit_log WHERE action = 'backup.restored'")
        )
    assert audit["source"] == source_id
    assert "passphrase" not in str(audit).lower()
    restored_sources = (await backup.client.get(f"{API}/backup/restore/sources")).json()
    assert any("pre_restore" in item["locations"] for item in restored_sources["sources"])


async def test_broken_file_and_wrong_passphrase_leave_database_alone(
    backup: BackupApp, engine: AsyncEngine, test_database_url: str, leftovers: None
) -> None:
    api = _api(backup)
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    a = await _start(api, setup, "Anna Probe")
    await api.shoot(setup.tid, a, FULL)
    source_id = await _snapshot_to_usb(backup)
    before = await _results(engine)

    # Falsches Passwort: Abbruch im ersten Schritt, keine Wartung, nichts angelegt.
    await backup.client.post(
        f"{API}/backup/restore/execute",
        json={"source_id": source_id, "passphrase": "ganz falsches Wort", "confirm": source_id},
    )
    failed = await _wait(backup.client)
    assert failed["state"] == "failed"
    assert failed["steps"][0]["state"] == "failed"
    assert "falsch" in failed["error_de"]
    assert failed["maintenance"] is False

    # Kaputte Datei: ein Byte mitten im verschlüsselten Strom gekippt.
    path = backup.env.usb_dir / "snapshots" / source_id.split(":", 1)[1]
    broken = _broken_copy(path)
    broken_id = f"usb:{broken.name}"
    preview = await backup.client.post(
        f"{API}/backup/restore/preview", json={"source_id": broken_id, "passphrase": PASSPHRASE}
    )
    assert preview.status_code == 400
    assert "beschädigt" in preview.json()["detail"]
    await backup.client.post(
        f"{API}/backup/restore/execute",
        json={"source_id": broken_id, "passphrase": PASSPHRASE, "confirm": broken_id},
    )
    failed = await _wait(backup.client)
    assert failed["state"] == "failed"
    assert "beschädigt" in failed["error_de"]

    assert await _results(engine) == before
    assert await _restore_databases(test_database_url) == []
    assert not backup.app.state.maintenance.active


async def _older_dump(test_database_url: str, target: Path, revision: str) -> None:
    """Abzug einer Datenbank im Stand `revision`, als Server-Abzug mit Prüfsumme."""
    from app.modules.backup import fsutil, pgtools

    name = make_url(test_database_url).database + "_restore_alt"
    await _drop(test_database_url, [name])
    admin = create_async_engine(
        make_url(test_database_url).set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    await admin.dispose()
    url = make_url(test_database_url).set(database=name).render_as_string(hide_password=False)
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            revision if revision != "zukunft" else "heads",
            cwd=BACKEND_DIR,
            env={**os.environ, "DATABASE_URL": url},
        )
        assert await process.wait() == 0
        if revision == "zukunft":
            other = create_async_engine(url)
            async with other.begin() as connection:
                await connection.execute(text("DELETE FROM alembic_version"))
                await connection.execute(text("INSERT INTO alembic_version VALUES ('9999_x')"))
            await other.dispose()
        target.parent.mkdir(parents=True, exist_ok=True)
        await pgtools.dump(pgtools.PgTarget.from_url(url), target, 120)
        fsutil.write_checksum(target, fsutil.sha256_file(target))
    finally:
        await _drop(test_database_url, [name])


async def test_older_schema_is_upgraded_newer_is_refused(
    backup: BackupApp, engine: AsyncEngine, test_database_url: str, leftovers: None
) -> None:
    snapshots = backup.env.data_dir / "backups" / "snapshots"
    await _older_dump(test_database_url, snapshots / "snapshot-20260101T100000Z.dump", "zukunft")
    newer = (
        await backup.client.post(
            f"{API}/backup/restore/preview",
            json={"source_id": "local:snapshot-20260101T100000Z.dump"},
        )
    ).json()
    assert newer["restorable"] is False
    assert newer["schema_check"]["state"] == "newer"
    assert [p["code"] for p in newer["problem_items"]] == ["schema_newer"]
    assert newer["problems"] == [newer["problem_items"][0]["message_de"]]

    await _older_dump(
        test_database_url, snapshots / "snapshot-20260102T100000Z.dump", "0015_auth_rechte"
    )
    source_id = "local:snapshot-20260102T100000Z.dump"
    preview = (
        await backup.client.post(f"{API}/backup/restore/preview", json={"source_id": source_id})
    ).json()
    assert preview["schema_check"]["state"] == "older", preview
    assert preview["restorable"] is True, preview["problems"]
    await backup.client.post(
        f"{API}/backup/restore/execute", json={"source_id": source_id, "confirm": source_id}
    )
    status = await _wait(backup.client)
    assert status["state"] == "succeeded", status
    assert status["result"]["schema_upgraded"] is True
    await engine.dispose()
    _known, heads = guided._revisions()
    async with engine.connect() as connection:
        versions = sorted(await connection.scalars(text("SELECT version_num FROM alembic_version")))
        roles = await connection.scalar(text("SELECT count(*) FROM role WHERE is_system"))
    assert versions == sorted(heads)
    # Die Module sind neu gestartet: Startrollen angelegt, Katalog importiert.
    assert roles == 1
    health = (await backup.client.get(f"{API}/health")).json()
    assert health["db"] == "ok"
    assert health["katalog"]["disziplinen"] > 0
