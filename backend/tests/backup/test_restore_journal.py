"""Wiederherstellung mit Mitschrift: Abzug einspielen, danach fehlende Ereignisse nachtragen."""

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.modules.backup import journal_apply, restore
from tests.backup.conftest import PASSPHRASE, BackupApp
from tests.conftest import BACKEND_DIR
from tests.ergebnisse.conftest import Api, Setup, make_setup, precision_definition, shots

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


async def _run_cli(*args: str, passphrase: str = PASSPHRASE) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.modules.backup.restore",
        *args,
        cwd=BACKEND_DIR,
        env={**os.environ, restore.PASSPHRASE_ENV: passphrase},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    assert process.returncode is not None
    return process.returncode, stderr.decode()


async def _drop(url: str, name: str) -> None:
    admin = create_async_engine(
        make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


async def _state(engine: AsyncEngine, start_ids: list[str]) -> dict[str, Any]:
    """Ereignisse, aktueller Stand und Start-Status – das, was nach dem Nachtragen stimmen muss."""
    params = {"ids": [uuid.UUID(sid) for sid in start_ids]}
    async with engine.connect() as connection:
        events = (
            await connection.execute(
                text(
                    "SELECT id, start_id, seq, type, payload, reason, user_id, device_id, "
                    "created_at "
                    "FROM result_event WHERE start_id = ANY(:ids) ORDER BY start_id, seq"
                ),
                params,
            )
        ).all()
        current = (
            await connection.execute(
                text(
                    "SELECT start_id, raw, score, is_final, finalized_at, provisional_until, "
                    "last_seq, needs_review FROM result_current WHERE start_id = ANY(:ids) "
                    "ORDER BY start_id"
                ),
                params,
            )
        ).all()
        starts = (
            await connection.execute(
                text(
                    "SELECT id, status, abort_reason, on_lane, queue_position FROM start "
                    "WHERE id = ANY(:ids) ORDER BY id"
                ),
                params,
            )
        ).all()
    return {"events": events, "current": current, "starts": starts}


async def _count_events(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return await connection.scalar(text("SELECT count(*) FROM result_event"))


# --- Hilfe ---------------------------------------------------------------------------


def test_help_names_passphrase_and_steps(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        restore.main(["--help"])
    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "SCHIESSHUB_BACKUP_PASSPHRASE" in help_text
    assert "--apply-journal" in help_text
    assert "--database-name" in help_text
    for step in ("entschlüsseln", "Prüfsumme", "keys", "pg_restore", "Mitschrift"):
        assert step in help_text, step


# --- Kompletter Weg: Abzug + Mitschrift vom Stick --------------------------------------


async def test_restore_with_journal_matches_source(
    backup: BackupApp, engine: AsyncEngine, test_database_url: str, tmp_path: Path
) -> None:
    api = _api(backup)
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    a = await _start(api, setup, "Alma Vorher")
    b = await _start(api, setup, "Bert Halb")
    c = await _start(api, setup, "Cora Wartet")
    await _start(api, setup, "Dora Später")  # bleibt angemeldet, ohne Ereignis
    await api.shoot(setup.tid, a, FULL)  # seq 1, 2
    await api.shoot(setup.tid, b, PARTIAL, final=False)  # seq 1, auf der Bahn

    await backup.client.put("/api/v1/backup/passphrase", json={"passphrase": PASSPHRASE})
    backup.env.plug_in()
    await backup.client.post("/api/v1/backup/usb/recheck")
    _local, usb_run = (await backup.client.post("/api/v1/backup/run")).json()
    assert usb_run["ok"], usb_run
    snapshot = backup.env.usb_dir / "snapshots" / usb_run["file_name"]

    # Nach der Sicherung: Korrektur und Wiederöffnen (A), Rest erfasst und abgeschlossen (B),
    # Abbruch (C), ein ganz neuer Start (E), der in der Sicherung fehlt.
    path_a = api.start_path(setup.tid, a)
    await api.ok(
        "POST",
        f"{path_a}/correct",
        json={"raw": shots([10] * 5, [9, 9, 9, 9, 8]), "reason": "Zählfehler", "base_seq": 2},
    )
    await api.ok("POST", f"{path_a}/reopen", json={"reason": "Scheibe vertauscht"})
    state = await api.put_raw(setup.tid, b, FULL, 1)
    await api.finalize(setup.tid, b, state["seq"])
    await api.ok(
        "POST",
        f"{api.start_path(setup.tid, c)}/result/abort",
        json={"abort_reason": "dns", "reason": "nicht erschienen"},
    )
    e = await _start(api, setup, "Emil Neu")
    await api.shoot(setup.tid, e, FULL)
    status = (await backup.client.post("/api/v1/backup/usb/recheck")).json()
    assert status["journal"]["pending"] == 0
    journal_dir = backup.env.usb_dir / "journal"
    assert list(journal_dir.glob("*.shbj"))

    source = await _state(engine, [a, b, c])
    target_name = make_url(test_database_url).database + "_journal"
    target_url = make_url(test_database_url).set(database=target_name)
    target = target_url.render_as_string(hide_password=False)
    await _drop(test_database_url, target_name)
    try:
        code, stderr = await _run_cli(
            str(snapshot),
            "--database-url",
            target,
            "--data-dir",
            str(tmp_path / "neu"),
            "--create-database",
            "--apply-journal",
            str(journal_dir),
        )
        assert code == restore.EXIT_INCOMPLETE, stderr
        assert "wiederhergestellt" in stderr
        assert "5 Ereignisse nachgetragen" in stderr, stderr
        assert "3 waren schon in der Sicherung" in stderr, stderr
        assert "2 übersprungen, weil der Start in der Sicherung fehlt" in stderr, stderr
        assert "Startnummer 5" in stderr, stderr

        restored = create_async_engine(target_url)
        try:
            after = await _state(restored, [a, b, c])
            assert after == source
            starts = {row.id: row for row in after["starts"]}
            assert starts[uuid.UUID(a)].status == "captured"
            assert starts[uuid.UUID(b)].status == "final"
            assert starts[uuid.UUID(c)].status == "aborted"
            assert starts[uuid.UUID(c)].abort_reason == "dns"
            events_before = await _count_events(restored)

            # Noch einmal: nichts Neues, nichts doppelt.
            code, stderr = await _run_cli(
                "--apply-journal", str(journal_dir), "--database-url", target
            )
            assert code == restore.EXIT_INCOMPLETE, stderr
            assert "0 Ereignisse nachgetragen" in stderr, stderr
            assert "8 waren schon in der Sicherung" in stderr, stderr
            assert await _count_events(restored) == events_before
            assert await _state(restored, [a, b, c]) == source
        finally:
            await restored.dispose()

        # Falsches Passwort für die Mitschrift: Abbruch mit Code 2, Datenbank unverändert.
        code, stderr = await _run_cli(
            "--apply-journal",
            str(journal_dir),
            "--database-url",
            target,
            passphrase="ein ganz anderes Passwort",
        )
        assert code == restore.EXIT_WRONG_PASSPHRASE, stderr
    finally:
        await _drop(test_database_url, target_name)


# --- Bausteine: Lücken, Widersprüche, fehlende Starts ----------------------------------


async def test_apply_skips_gaps_conflicts_and_unknown_starts(
    backup: BackupApp, engine: AsyncEngine
) -> None:
    api = _api(backup)
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    a = await _start(api, setup, "Anton Lücke")
    b = await _start(api, setup, "Berta Doppelt")
    await api.shoot(setup.tid, a, PARTIAL, final=False)  # seq 1
    await api.shoot(setup.tid, b, PARTIAL, final=False)  # seq 1
    entries = [
        entry
        for path in sorted((backup.env.data_dir / "backups" / "journal").glob("*.ndjson"))
        for entry in journal_apply.load_journal(path, None)
    ]
    records = journal_apply.result_records(entries)
    assert len(records) == 2
    by_start = {record["start_id"]: record for record in records}

    def variant(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
        return {**base, "event_id": str(uuid.uuid4()), **changes}

    gap = variant(by_start[a], seq=3, type="finalized", payload={"provisional_until": None})
    clash = variant(by_start[b], seq=1)
    unknown = variant(by_start[a], start_id=str(uuid.uuid4()), start_number=99)
    before = await _count_events(engine)

    report = await journal_apply.apply_records(
        backup.app.state.session_factory, [*records, gap, clash, unknown]
    )
    assert report.applied == 0
    assert report.present == 2
    assert report.missing_events == 1
    assert [item.start_number for item in report.missing_starts] == [99]
    assert len(report.conflicts) == 2
    texts = " ".join(report.conflicts)
    assert "Lücke" in texts
    assert "anderem Inhalt" in texts
    assert await _count_events(engine) == before
    lines = report.summary()
    assert lines[0].startswith("0 Ereignisse nachgetragen, 2 waren schon in der Sicherung")
    # Dieselben Starts als Liste für die Oberfläche: erst der unbekannte, dann die unpassenden.
    skipped = report.skipped_starts()
    numbers = {a: by_start[a].get("start_number"), b: by_start[b].get("start_number")}
    assert [(s.reason_code, s.start_number) for s in skipped] == [
        ("start_not_in_backup", 99),
        *sorted(("does_not_match", number) for number in numbers.values()),
    ]
    # Der Wettbewerb steht in der Datenbank, also kennt die Liste seinen Namen.
    assert len({s.competition_name for s in skipped}) == 1
    assert skipped[0].competition_name
    assert all(s.message_de for s in skipped)


async def test_apply_brings_status_and_current_in_line(
    backup: BackupApp, engine: AsyncEngine
) -> None:
    """Ein Ereignis, das in der Datenbank fehlt, wird angehängt; Stand und Status folgen."""
    api = _api(backup)
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    a = await _start(api, setup, "Anna Probe")
    await api.shoot(setup.tid, a, FULL)  # seq 1 raw_set, seq 2 finalized
    entries = [
        entry
        for path in sorted((backup.env.data_dir / "backups" / "journal").glob("*.ndjson"))
        for entry in journal_apply.load_journal(path, None)
    ]
    records = journal_apply.result_records(entries)
    finalized = next(record for record in records if record["type"] == "finalized")
    expected = await _state(engine, [a])
    # Wie eine Sicherung zwischen Erfassen und Abschließen: das Abschluss-Ereignis fehlt.
    async with engine.begin() as connection:
        await connection.execute(text("ALTER TABLE result_event DISABLE TRIGGER USER"))
        await connection.execute(
            text("DELETE FROM result_event WHERE id = :id"),
            {"id": uuid.UUID(finalized["event_id"])},
        )
        await connection.execute(text("ALTER TABLE result_event ENABLE TRIGGER USER"))
        await connection.execute(
            text(
                "UPDATE result_current SET is_final = false, finalized_at = NULL, last_seq = 1 "
                "WHERE start_id = :id"
            ),
            {"id": uuid.UUID(a)},
        )
        await connection.execute(
            text("UPDATE start SET status = 'captured', on_lane = true WHERE id = :id"),
            {"id": uuid.UUID(a)},
        )

    report = await journal_apply.apply_records(backup.app.state.session_factory, records)
    assert (report.applied, report.present, report.conflicts) == (1, 1, [])
    assert report.recomputed_competitions == 1
    assert await _state(engine, [a]) == expected


async def test_install_keys_accepts_identical_files(tmp_path: Path) -> None:
    source = tmp_path / "aus-sicherung"
    source.mkdir()
    (source / "field-keys.json").write_text('{"format": 1}', encoding="utf-8")
    target = tmp_path / "server"
    (target / "keys").mkdir(parents=True)
    (target / "keys" / "field-keys.json").write_text('{"format": 1}', encoding="utf-8")
    assert restore.install_keys(source, target) == []
    (target / "keys" / "field-keys.json").write_text('{"format": 2}', encoding="utf-8")
    with pytest.raises(restore.RestoreError, match="bereits andere Schlüssel"):
        restore.install_keys(source, target)


async def test_apply_takes_back_an_undone_abort(backup: BackupApp, engine: AsyncEngine) -> None:
    """`abort_undone` aus der Mitschrift: Ereignis angehängt, Start wieder „erfasst“."""
    api = _api(backup)
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    a = await _start(api, setup, "Anna Zurück")
    await api.shoot(setup.tid, a, PARTIAL, final=False)  # seq 1
    path = api.start_path(setup.tid, a)
    await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dnf"})  # seq 2
    await api.ok("POST", f"{path}/result/undo-abort", json={"reason": "Versehen"})  # seq 3
    entries = [
        entry
        for path in sorted((backup.env.data_dir / "backups" / "journal").glob("*.ndjson"))
        for entry in journal_apply.load_journal(path, None)
    ]
    records = journal_apply.result_records(entries)
    undone = next(record for record in records if record["type"] == "abort_undone")
    assert undone["payload"] == {"undone_abort_reason": "dnf", "status": "captured"}
    expected = await _state(engine, [a])
    # Wie eine Sicherung zwischen Abbruch und Rücknahme.
    async with engine.begin() as connection:
        await connection.execute(text("ALTER TABLE result_event DISABLE TRIGGER USER"))
        await connection.execute(
            text("DELETE FROM result_event WHERE id = :id"), {"id": uuid.UUID(undone["event_id"])}
        )
        await connection.execute(text("ALTER TABLE result_event ENABLE TRIGGER USER"))
        await connection.execute(
            text("UPDATE result_current SET last_seq = 2 WHERE start_id = :id"),
            {"id": uuid.UUID(a)},
        )
        await connection.execute(
            text("UPDATE start SET status = 'aborted', abort_reason = 'dnf' WHERE id = :id"),
            {"id": uuid.UUID(a)},
        )

    report = await journal_apply.apply_records(backup.app.state.session_factory, records)
    assert (report.applied, report.present, report.conflicts) == (1, 2, [])
    assert report.status_changes == 1
    assert await _state(engine, [a]) == expected
