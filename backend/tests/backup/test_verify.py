"""„Prüfen“ einer Sicherung: einmal lesen, nicht hinter Stick-Kopien warten, Event-Loop frei."""

import asyncio
import threading
import time
from pathlib import Path

import pytest

from app.modules.backup import crypto, fsutil
from tests.backup.conftest import PASSPHRASE, BackupApp

API = "/api/v1"


async def _usb_run(backup: BackupApp) -> dict:
    await backup.client.put(f"{API}/backup/passphrase", json={"passphrase": PASSPHRASE})
    backup.env.plug_in()
    await backup.client.post(f"{API}/backup/usb/recheck")
    _local, usb_run = (await backup.client.post(f"{API}/backup/run")).json()
    assert usb_run["ok"], usb_run
    return usb_run


async def _verify(backup: BackupApp, run_id: str) -> dict:
    response = await backup.client.post(
        f"{API}/backup/runs/{run_id}/verify", json={"passphrase": PASSPHRASE}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_verify_reads_stick_file_once(
    backup: BackupApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    usb_run = await _usb_run(backup)
    copy = backup.env.usb_dir / "snapshots" / usb_run["file_name"]
    opened: list[Path] = []
    real_open = Path.open

    def counting_open(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if self == copy:
            opened.append(self)
        return real_open(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", counting_open)
    monkeypatch.setattr(
        fsutil, "sha256_file", lambda *a, **k: pytest.fail("Datei ein zweites Mal gelesen")
    )
    result = await _verify(backup, usb_run["id"])
    assert result["ok"] is True, result
    assert result["checksum_ok"] is True
    assert len(opened) == 1

    # Stimmt die Prüfsummendatei nicht, fällt das trotzdem auf.
    fsutil.checksum_path(copy).write_text("0" * 64 + "  x\n", encoding="ascii")
    broken = await _verify(backup, usb_run["id"])
    assert broken["ok"] is False
    assert broken["checksum_ok"] is False
    assert broken["error"] == "Die Prüfsumme der Datei auf dem Stick weicht ab."


async def test_verify_does_not_wait_for_running_stick_write(backup: BackupApp) -> None:
    """Eine laufende Kopie auf den Stick (eigener Thread) hält die Prüfung nicht auf."""
    usb_run = await _usb_run(backup)
    release = threading.Event()
    loop = asyncio.get_running_loop()
    busy = loop.run_in_executor(backup.service._usb_executor, release.wait, 30)
    try:
        started = time.perf_counter()
        result = await asyncio.wait_for(_verify(backup, usb_run["id"]), 10)
        assert result["ok"] is True
        assert time.perf_counter() - started < 5
    finally:
        release.set()
        await busy


async def test_verify_keeps_event_loop_free(
    backup: BackupApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auch eine langsame Schlüsselableitung (schwacher Server) blockiert keine anderen Anfragen."""
    usb_run = await _usb_run(backup)
    real_unwrap = crypto.unwrap_key

    def slow_unwrap(header: bytes, passphrase: str) -> crypto.BackupKey:
        time.sleep(1.0)
        return real_unwrap(header, passphrase)

    monkeypatch.setattr(crypto, "unwrap_key", slow_unwrap)
    lags: list[float] = []
    done = asyncio.Event()

    async def ticker() -> None:
        while not done.is_set():
            before = time.perf_counter()
            await asyncio.sleep(0.01)
            lags.append(time.perf_counter() - before - 0.01)

    tick = asyncio.create_task(ticker())
    verify = asyncio.create_task(_verify(backup, usb_run["id"]))
    await asyncio.sleep(0.3)
    # Während die Prüfung läuft, antwortet der Server auf andere Anfragen.
    started = time.perf_counter()
    status = await backup.client.get(f"{API}/backup/status")
    assert status.status_code == 200
    assert time.perf_counter() - started < 0.5
    assert not verify.done()
    result = await verify
    done.set()
    await tick
    assert result["ok"] is True
    assert max(lags) < 0.25, max(lags)


async def test_verify_is_fast(backup: BackupApp) -> None:
    usb_run = await _usb_run(backup)
    started = time.perf_counter()
    result = await _verify(backup, usb_run["id"])
    assert result["ok"] is True
    # Abzug einer leeren Testdatenbank: Schlüsselableitung (≈ 0,1 s) plus pg_restore --list.
    assert time.perf_counter() - started < 3
