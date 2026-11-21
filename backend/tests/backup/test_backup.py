"""Sicherung im Zusammenspiel: echte Datenbank, echtes pg_dump/pg_restore, Stick als Verzeichnis."""

import asyncio
import errno
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.modules.backup import archive, crypto, journal, pgtools, service, usb
from tests.backup.conftest import PASSPHRASE, BackupApp, StartBackup
from tests.conftest import BACKEND_DIR


async def _set_passphrase(backup: BackupApp) -> None:
    response = await backup.client.put("/api/v1/backup/passphrase", json={"passphrase": PASSPHRASE})
    assert response.status_code == 200, response.text


async def _run(backup: BackupApp) -> list[dict]:
    response = await backup.client.post("/api/v1/backup/run")
    assert response.status_code == 200, response.text
    return response.json()


async def _status(backup: BackupApp) -> dict:
    response = await backup.client.get("/api/v1/backup/status")
    assert response.status_code == 200
    return response.json()


async def _recheck(backup: BackupApp) -> dict:
    response = await backup.client.post("/api/v1/backup/usb/recheck")
    assert response.status_code == 200
    return response.json()


def _decrypt_archive(path: Path, passphrase: str, target: Path) -> archive.ArchiveContents:
    with path.open("rb") as file:
        reader = crypto.DecryptingReader(file, passphrase=passphrase)
        contents = archive.read_archive(reader, target)
        reader.finish()
    return contents


# --- Einstellungen --------------------------------------------------------------------


async def test_settings_defaults_and_validation(backup: BackupApp) -> None:
    response = await backup.client.get("/api/v1/backup/settings")
    assert response.json() == {
        "enabled": True,
        "usb_enabled": True,
        "snapshot_interval_minutes": 5,
        "keep_local": 20,
        "keep_usb": 20,
        "warn_all_stations": True,
        "warn_on_display": False,
        "encrypt": True,
    }
    changed = {**response.json(), "keep_usb": 3, "warn_on_display": True}
    assert (await backup.client.put("/api/v1/backup/settings", json=changed)).json() == changed

    for invalid in ({**changed, "keep_local": 0}, {**changed, "unbekannt": 1}, {"enabled": "ja"}):
        assert (await backup.client.put("/api/v1/backup/settings", json=invalid)).status_code == 422
    # Gespeichert in der Tabelle `setting` und nach einem Neustart wieder da.
    assert (await backup.client.get("/api/v1/backup/settings")).json() == changed


async def test_settings_survive_restart(idle_scheduler: None, start_backup: StartBackup) -> None:
    async with start_backup() as first:
        settings = (await first.client.get("/api/v1/backup/settings")).json()
        await first.client.put("/api/v1/backup/settings", json={**settings, "keep_local": 7})
    async with start_backup() as second:
        assert (await second.client.get("/api/v1/backup/settings")).json()["keep_local"] == 7
        assert second.service.config.keep_local == 7


# --- Stick fehlt / Passwort fehlt ------------------------------------------------------


async def test_missing_marker_means_no_write_and_warning(backup: BackupApp) -> None:
    await _set_passphrase(backup)
    status = await _status(backup)
    assert status["usb"]["present"] is False
    assert status["warning"]["code"] == "usb_missing"

    local, usb_run = await _run(backup)
    assert local["ok"] is True
    assert usb_run["ok"] is False
    assert usb_run["error"] == "Kein Sicherungs-Stick gefunden."
    # Das Verzeichnis ist da und beschreibbar – trotzdem darf ohne Marker nichts hinein.
    assert list(backup.env.usb_dir.iterdir()) == []
    assert len(backup.env.local_snapshots()) == 1


async def test_marker_removed_just_before_write_is_respected(backup: BackupApp) -> None:
    await _set_passphrase(backup)
    backup.env.plug_in()
    await _recheck(backup)
    # Der Stick verschwindet zwischen Prüfung und Schreiben.
    backup.env.pull_out()
    local, usb_run = await _run(backup)
    assert local["ok"] is True
    assert usb_run["ok"] is False
    assert backup.env.usb_files() == []


async def test_no_plain_copy_without_passphrase(backup: BackupApp) -> None:
    backup.env.plug_in()
    status = await _recheck(backup)
    assert status["passphrase_set"] is False
    assert status["warning"]["code"] == "passphrase_missing"
    assert "Sicherungspasswort fehlt" in status["warning"]["message_de"]

    _, usb_run = await _run(backup)
    assert usb_run["ok"] is False
    assert "Sicherungspasswort fehlt" in usb_run["error"]
    await backup.service.append_journal({"ergebnis": 1})
    await _recheck(backup)
    assert backup.env.usb_files() == []
    assert (await _status(backup))["journal"]["pending"] == 1


# --- Abzug, Verschlüsselung, Prüfung --------------------------------------------------


async def test_snapshot_local_and_encrypted_on_usb(backup: BackupApp, tmp_path: Path) -> None:
    keys_dir = backup.env.data_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / "field.key").write_bytes(b"feldschluessel-fuer-namen")
    await _set_passphrase(backup)
    backup.env.plug_in()
    status = await _recheck(backup)
    assert status["warning"] is None
    assert status["usb"]["present"] is True
    assert status["usb"]["writable"] is True

    local, usb_run = await _run(backup)
    assert local["ok"], local
    assert usb_run["ok"], usb_run

    dump = backup.env.data_dir / "backups" / "snapshots" / local["file_name"]
    assert dump.read_bytes().startswith(b"PGDMP")
    sha_file = dump.with_name(dump.name + ".sha256").read_text()
    assert sha_file.split()[0] == local["sha256"]
    assert not list(dump.parent.glob("*.tmp"))

    copy = backup.env.usb_dir / "snapshots" / usb_run["file_name"]
    assert copy.suffix == ".shb"
    raw = copy.read_bytes()
    assert raw.startswith(crypto.MAGIC)
    assert b"PGDMP" not in raw
    assert b"feldschluessel" not in raw
    assert copy.with_name(copy.name + ".sha256").read_text().split()[0] == usb_run["sha256"]

    contents = _decrypt_archive(copy, PASSPHRASE, tmp_path / "out")
    assert contents.database_sha256_ok
    assert contents.manifest["database"]["sha256"] == local["sha256"]
    # Das komplette Schlüsselverzeichnis kommt mit, auch der Feldschlüssel anderer Module.
    key_entries = {f"keys/{path.relative_to(keys_dir).as_posix()}" for path in keys_dir.rglob("*")}
    assert {"keys/backup-key.json", "keys/field.key"} <= key_entries
    assert set(contents.entries) == {"manifest.json", "database.dump", *key_entries}
    assert (tmp_path / "out" / "keys" / "field.key").read_bytes() == b"feldschluessel-fuer-namen"
    toc = await pgtools.list_contents(tmp_path / "out" / "database.dump")
    assert any("catalog_discipline" in line for line in toc)

    with pytest.raises(crypto.WrongPassphraseError):
        _decrypt_archive(copy, "ein ganz anderes Passwort", tmp_path / "wrong")

    status = await _status(backup)
    assert status["last_snapshot"]["id"] == local["id"]
    assert status["last_usb_copy"]["id"] == usb_run["id"]


async def test_verify_endpoint(backup: BackupApp) -> None:
    await _set_passphrase(backup)
    backup.env.plug_in()
    await _recheck(backup)
    local, usb_run = await _run(backup)

    url = f"/api/v1/backup/runs/{usb_run['id']}/verify"
    result = (await backup.client.post(url, json={"passphrase": PASSPHRASE})).json()
    assert result["ok"] is True, result
    assert result["checksum_ok"] is True
    assert result["database_toc_entries"] > 10
    assert "keys/backup-key.json" in result["entries"]

    wrong = await backup.client.post(url, json={"passphrase": "ein ganz anderes Passwort"})
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "Das Sicherungspasswort ist falsch."
    missing = await backup.client.post(url, json={})
    assert missing.status_code == 400
    assert "Sicherungspasswort angeben" in missing.json()["detail"]

    # Beschädigte Kopie: Prüfung meldet den Fehler, statt zu scheitern.
    copy = backup.env.usb_dir / "snapshots" / usb_run["file_name"]
    data = bytearray(copy.read_bytes())
    data[-100] ^= 0xFF
    copy.write_bytes(bytes(data))
    broken = (await backup.client.post(url, json={"passphrase": PASSPHRASE})).json()
    assert broken["ok"] is False
    assert "beschädigt" in broken["error"]

    local_result = (
        await backup.client.post(f"/api/v1/backup/runs/{local['id']}/verify", json={})
    ).json()
    assert local_result["ok"] is True
    assert local_result["location"] == "local"

    unknown = await backup.client.post(
        "/api/v1/backup/runs/00000000-0000-0000-0000-000000000000/verify", json={}
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Diesen Sicherungslauf gibt es nicht."


async def test_download_is_encrypted_with_passphrase(backup: BackupApp, tmp_path: Path) -> None:
    local, _ = await _run(backup)
    url = f"/api/v1/backup/runs/{local['id']}/download"
    refused = await backup.client.get(url)
    assert refused.status_code == 409
    assert "Sicherungspasswort" in refused.json()["detail"]

    await _set_passphrase(backup)
    response = await backup.client.get(url)
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('.shb"')
    target = tmp_path / "download.shb"
    target.write_bytes(response.content)
    contents = _decrypt_archive(target, PASSPHRASE, tmp_path / "out")
    assert contents.manifest["database"]["sha256"] == local["sha256"]
    # Die temporäre Datei ist nach der Auslieferung wieder weg.
    assert list((backup.env.data_dir / "backups" / "tmp").iterdir()) == []


async def test_passphrase_change_requires_current(backup: BackupApp) -> None:
    await _set_passphrase(backup)
    first_key = backup.service.key
    url = "/api/v1/backup/passphrase"
    response = await backup.client.put(url, json={"passphrase": "noch ein langes Passwort"})
    assert response.status_code == 409
    response = await backup.client.put(
        url, json={"passphrase": "noch ein langes Passwort", "current_passphrase": "falsch!!!!!!"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Das bisherige Sicherungspasswort stimmt nicht."
    response = await backup.client.put(
        url, json={"passphrase": "noch ein langes Passwort", "current_passphrase": PASSPHRASE}
    )
    assert response.status_code == 200
    assert backup.service.key != first_key
    assert (await backup.client.put(url, json={"passphrase": "kurz"})).status_code == 422


# --- Rotation ---------------------------------------------------------------------------


async def test_rotation_local_and_usb_separately(backup: BackupApp) -> None:
    await _set_passphrase(backup)
    backup.env.plug_in()
    await _recheck(backup)
    settings = (await backup.client.get("/api/v1/backup/settings")).json()
    await backup.client.put(
        "/api/v1/backup/settings", json={**settings, "keep_local": 2, "keep_usb": 1}
    )
    names = []
    for _ in range(3):
        local, usb_run = await _run(backup)
        assert local["ok"]
        assert usb_run["ok"]
        names.append((local["file_name"], usb_run["file_name"]))

    assert [path.name for path in backup.env.local_snapshots()] == [n[0] for n in names[1:]]
    usb_snapshots = sorted(p.name for p in (backup.env.usb_dir / "snapshots").iterdir())
    assert usb_snapshots == [names[2][1], names[2][1] + ".sha256"]

    runs = (await backup.client.get("/api/v1/backup/runs", params={"target": "local"})).json()
    assert [run["file_name"] for run in runs] == [n[0] for n in reversed(names)]
    gone = await backup.client.get(f"/api/v1/backup/runs/{runs[-1]['id']}/download")
    assert gone.status_code == 404


# --- Stick voll, nicht beschreibbar, hängt -------------------------------------------


async def test_usb_full(backup: BackupApp, monkeypatch: pytest.MonkeyPatch) -> None:
    await _set_passphrase(backup)
    backup.env.plug_in()
    real_usage = usb.shutil.disk_usage
    monkeypatch.setattr(usb.shutil, "disk_usage", lambda path: real_usage(path)._replace(free=1000))
    status = await _recheck(backup)
    assert status["warning"]["code"] == "usb_full"
    _, usb_run = await _run(backup)
    assert usb_run["ok"] is False
    assert "nicht genug Platz" in usb_run["error"]
    assert backup.env.usb_files() == []


async def test_usb_runs_out_of_space_while_writing(
    backup: BackupApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _set_passphrase(backup)
    backup.env.plug_in()
    await _recheck(backup)

    def disk_full(*args: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(service.archive, "write_archive", disk_full)
    local, usb_run = await _run(backup)
    assert local["ok"] is True
    assert usb_run["error"] == "Auf dem Sicherungs-Stick ist kein Platz mehr."
    # Keine halbe Datei auf dem Stick.
    assert backup.env.usb_files() == []
    assert (await _status(backup))["warning"]["code"] == "usb_copy_failed"


@pytest.mark.skipif(os.geteuid() == 0, reason="root darf trotz fehlender Rechte schreiben")
async def test_usb_not_writable(backup: BackupApp) -> None:
    await _set_passphrase(backup)
    backup.env.plug_in()
    backup.env.usb_dir.chmod(0o555)
    try:
        status = await _recheck(backup)
        assert status["usb"]["present"] is True
        assert status["usb"]["writable"] is False
        assert status["warning"]["code"] == "usb_not_writable"
        _, usb_run = await _run(backup)
        assert usb_run["ok"] is False
        assert usb_run["error"] == "Der Sicherungs-Stick ist nicht beschreibbar."
    finally:
        backup.env.usb_dir.chmod(0o755)
    assert backup.env.usb_files() == []


async def test_hanging_usb_does_not_block(
    backup: BackupApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _set_passphrase(backup)
    backup.env.plug_in()
    await _recheck(backup)
    release = asyncio.Event()
    loop = asyncio.get_running_loop()

    def hang(*args: object) -> None:
        asyncio.run_coroutine_threadsafe(release.wait(), loop).result(timeout=10)

    monkeypatch.setattr(backup.service, "_write_usb_snapshot", hang)
    backup.service.usb_copy_timeout_seconds = 0.3
    local, usb_run = await asyncio.wait_for(_run(backup), timeout=30)
    assert local["ok"] is True
    assert usb_run["error"] == "Der Sicherungs-Stick hat nicht rechtzeitig geantwortet."
    # Die Anwendung antwortet weiter, auch während der Stick-Thread noch hängt.
    assert (await backup.client.get("/api/v1/backup/status")).status_code == 200
    release.set()


# --- Mitschrift: Stick wird gezogen und wieder eingesteckt ----------------------------


async def test_journal_catches_up_after_reinsert(backup: BackupApp) -> None:
    await _set_passphrase(backup)
    backup.env.plug_in()
    await _recheck(backup)
    for n in range(3):
        await service.append_journal({"start": n, "ringe": 90 + n})
    assert (await _status(backup))["journal"]["pending"] == 3
    status = await _recheck(backup)
    assert status["journal"]["pending"] == 0
    usb_journal = next((backup.env.usb_dir / "journal").glob("*.shbj"))
    assert [e.seq for e in journal.read_journal_file(usb_journal, PASSPHRASE)] == [1, 2, 3]

    backup.env.pull_out()
    before = usb_journal.read_bytes()
    for n in range(3, 5):
        await service.append_journal({"start": n})
    status = await _recheck(backup)
    assert status["usb"]["present"] is False
    assert status["warning"]["code"] == "usb_missing"
    assert status["journal"]["pending"] == 2
    assert usb_journal.read_bytes() == before
    # Lokal ist alles sofort da.
    local_segment = backup.service.journal.segment_paths()[0]
    assert len(journal.read_entries(local_segment)) == 5

    backup.env.plug_in()
    status = await _recheck(backup)
    assert status["journal"]["pending"] == 0
    assert status["warning"] is None
    entries = journal.read_journal_file(usb_journal, PASSPHRASE)
    assert [e.seq for e in entries] == [1, 2, 3, 4, 5]


async def test_reinserted_stick_gets_latest_snapshot(backup: BackupApp) -> None:
    await _set_passphrase(backup)
    local, usb_run = await _run(backup)
    assert usb_run["ok"] is False
    backup.env.plug_in()
    await _recheck(backup)
    copies = list((backup.env.usb_dir / "snapshots").glob("*.shb"))
    assert [c.name for c in copies] == [local["file_name"].removesuffix(".dump") + ".shb"]
    assert (await _status(backup))["last_usb_copy"]["ok"] is True


async def test_journal_restart_continues_sequence(
    idle_scheduler: None, start_backup: StartBackup
) -> None:
    async with start_backup():
        await service.append_journal({"a": 1})
        await service.append_journal({"a": 2})
    async with start_backup() as second:
        assert await service.append_journal({"a": 3}) == 3
        # Ohne Stick seit dem Start ist alles unbestätigt.
        assert (await _status(second))["journal"]["pending"] == 3
    with pytest.raises(RuntimeError):
        await service.append_journal({"a": 4})


# --- Stick einrichten -------------------------------------------------------------------


async def test_initialize_usb(backup: BackupApp) -> None:
    url = "/api/v1/backup/usb/initialize"
    assert (await backup.client.post(url, json={"confirm": False})).status_code == 422
    assert (await backup.client.post(url, json={})).status_code == 422
    response = await backup.client.post(url, json={"confirm": True})
    assert response.status_code == 200
    assert response.json()["usb"]["present"] is True
    assert backup.env.marker_path.is_file()
    again = await backup.client.post(url, json={"confirm": True})
    assert again.status_code == 409
    assert again.json()["detail"] == "Dieser Stick ist bereits als Sicherungs-Stick eingerichtet."


# --- Zeitplan und Ereignisse --------------------------------------------------------------


async def test_scheduler_runs_and_stops(start_backup: StartBackup) -> None:
    async with start_backup() as started:
        backup_service = started.service
        events = started.app.state.events.subscribe()
        backup_service.usb_check_seconds = 0.05
        # Abzug sofort fällig.
        backup_service._last_snapshot_at = service._now() - timedelta(hours=1)
        backup_service.wake()
        names: list[str] = []
        async with asyncio.timeout(30):
            while "backup.completed" not in names:
                names.append((await events.get()).name)
        # Stick einstecken: Der Task bemerkt es von selbst und meldet den Statuswechsel.
        started.env.plug_in()
        async with asyncio.timeout(10):
            while True:
                event = await events.get()
                if event.name == "backup.status" and event.data["usb"]["present"]:
                    break
        task = backup_service._task
    assert task is not None
    # Mit dem Ende der Anwendung endet auch der Hintergrund-Task.
    await asyncio.wait({task}, timeout=5)
    assert task.cancelled()


# --- Wiederherstellung -------------------------------------------------------------------


async def _drop(engine_url: str, name: str) -> None:
    admin = create_async_engine(
        make_url(engine_url).set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


async def test_restore_into_fresh_database(
    backup: BackupApp, engine: AsyncEngine, test_database_url: str, tmp_path: Path
) -> None:
    keys_dir = backup.env.data_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / "field.key").write_bytes(b"feldschluessel")
    await _set_passphrase(backup)
    backup.env.plug_in()
    await _recheck(backup)
    async with engine.connect() as connection:
        expected = await connection.scalar(text("SELECT count(*) FROM catalog_discipline"))
    assert expected > 0
    _, usb_run = await _run(backup)
    copy = backup.env.usb_dir / "snapshots" / usb_run["file_name"]

    target_name = make_url(test_database_url).database + "_restore"
    target_url = make_url(test_database_url).set(database=target_name)
    await _drop(test_database_url, target_name)
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.modules.backup.restore",
            str(copy),
            "--database-url",
            target_url.render_as_string(hide_password=False),
            "--data-dir",
            str(tmp_path / "new-server"),
            "--create-database",
            cwd=BACKEND_DIR,
            env={**os.environ, "SCHIESSHUB_BACKUP_PASSPHRASE": PASSPHRASE},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()
        assert process.returncode == 0, stderr.decode()
        assert "wiederhergestellt" in stderr.decode()

        restored = create_async_engine(target_url)
        async with restored.connect() as connection:
            count = await connection.scalar(text("SELECT count(*) FROM catalog_discipline"))
        await restored.dispose()
        assert count == expected
        new_keys = tmp_path / "new-server" / "keys"
        assert (new_keys / "field.key").read_bytes() == b"feldschluessel"
        assert crypto.load_key(new_keys) == backup.service.key

        # Zweiter Versuch: Ziel nicht leer, Schlüssel vorhanden -> Abbruch ohne Überschreiben.
        again = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.modules.backup.restore",
            str(copy),
            "--database-url",
            target_url.render_as_string(hide_password=False),
            "--data-dir",
            str(tmp_path / "new-server"),
            cwd=BACKEND_DIR,
            env={**os.environ, "SCHIESSHUB_BACKUP_PASSPHRASE": PASSPHRASE},
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await again.communicate()
        assert again.returncode == 1
        assert "bereits Schlüssel" in stderr.decode()

        wrong = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.modules.backup.restore",
            str(copy),
            "--database-url",
            target_url.render_as_string(hide_password=False),
            cwd=BACKEND_DIR,
            env={**os.environ, "SCHIESSHUB_BACKUP_PASSPHRASE": "ein ganz anderes Passwort"},
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await wrong.communicate()
        assert wrong.returncode == 2
        assert "Sicherungspasswort ist falsch" in stderr.decode()
    finally:
        await _drop(test_database_url, target_name)


# --- Kein Passwort in Prozessargumenten oder Logs ----------------------------------------


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


async def test_password_never_in_arguments_or_logs(
    backup: BackupApp,
    test_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_password = make_url(test_database_url).password
    assert db_password
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []
    passfiles: list[Path] = []
    original = asyncio.create_subprocess_exec

    async def spy(*args: str, **kwargs: object):
        env = kwargs.get("env") or {}
        calls.append((args, dict(env)))  # type: ignore[arg-type]
        if "PGPASSFILE" in env:  # type: ignore[operator]
            passfile = Path(env["PGPASSFILE"])  # type: ignore[index]
            passfiles.append(passfile)
            assert _mode(passfile) == 0o600
        return await original(*args, **kwargs)

    monkeypatch.setattr(pgtools.asyncio, "create_subprocess_exec", spy)
    monkeypatch.setenv("PGPASSWORD", db_password)
    caplog.set_level(logging.DEBUG)
    await _set_passphrase(backup)
    backup.env.plug_in()
    await _recheck(backup)
    local, usb_run = await _run(backup)
    assert local["ok"]
    assert usb_run["ok"]

    dumps = [args for args, _ in calls if Path(args[0]).name == "pg_dump" and len(args) > 2]
    assert dumps, calls
    for args, env in calls:
        assert not any(db_password in arg or PASSPHRASE in arg for arg in args)
        assert "PGPASSWORD" not in env
    assert passfiles
    assert not any(path.exists() for path in passfiles)
    for record in caplog.records:
        message = record.getMessage()
        assert db_password not in message
        assert PASSPHRASE not in message
