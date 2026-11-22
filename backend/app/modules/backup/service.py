"""Sicherung: Zeitplan, Abzüge, Kopie auf den Stick, Mitschrift und Überwachung des Sticks.

Ablauf eines Abzugs: pg_dump nach `data_dir/backups/snapshots` (tmp → fsync → rename, SHA-256
daneben), dann – wenn der Stick steckt – ein Archiv aus Abzug und Schlüsselverzeichnis,
verschlüsselt auf den Stick (tmp → fsync → rename, Prüfsumme, Zurücklesen und Vergleichen).
Alles, was den Stick berührt, läuft in einem eigenen Thread mit Zeitlimit; ein hängender oder
abgezogener Stick bremst die Anwendung nicht, sondern wird gemeldet.
"""

import asyncio
import contextlib
import errno
import functools
import logging
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select

from app import __version__
from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.events import EventHub
from app.core.settings_store import get_setting, put_setting
from app.modules.backup import archive, crypto, fsutil, journal, pgtools, usb
from app.modules.backup.models import (
    KIND_JOURNAL,
    KIND_SNAPSHOT,
    TARGET_LOCAL,
    TARGET_USB,
    BackupRun,
)
from app.modules.backup.schemas import (
    SETTINGS_KEY,
    BackupSettings,
    BackupStatusOut,
    JournalStatusOut,
    PassphraseOut,
    RunOut,
    UsbStatusOut,
    VerifyOut,
    WarningOut,
)

logger = logging.getLogger("schiesshub.backup")

EVENT_STATUS = "backup.status"
EVENT_COMPLETED = "backup.completed"
EVENT_FAILED = "backup.failed"

SNAPSHOT_PREFIX = "snapshot-"
LOCAL_SUFFIX = ".dump"
USB_ENCRYPTED_SUFFIX = ".shb"
USB_PLAIN_SUFFIX = ".tar"
# Reserve auf dem Stick zusätzlich zur Größe des letzten Abzugs.
USB_RESERVE_BYTES = 1024 * 1024


class BackupError(Exception):
    """Fehler mit einer Meldung für Anwender (HTTP 400)."""


class ConflictError(BackupError):
    """Aktion im aktuellen Zustand nicht möglich (HTTP 409)."""


class NotFoundError(BackupError):
    """HTTP 404."""


_active: BackupService | None = None


async def append_journal(record: dict[str, Any]) -> int:
    """Schreibt einen Eintrag in die laufende Mitschrift und liefert seine laufende Nummer.

    Die Zeile ist bei der Rückkehr lokal auf der Platte (fsync). Auf den Stick kommt sie
    gebündelt innerhalb weniger Sekunden; fehlt der Stick, wird nach dem Einstecken nachgezogen.
    """
    if _active is None:
        raise RuntimeError("Das Sicherungsmodul ist nicht gestartet.")
    return await _active.append_journal(record)


@dataclass(slots=True)
class _UsbState:
    present: bool = False
    writable: bool = False
    free_bytes: int | None = None
    last_seen_at: datetime | None = None
    error: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _usb_error_message(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "Der Sicherungs-Stick hat nicht rechtzeitig geantwortet."
    if isinstance(exc, (usb.UsbUnavailableError, crypto.BackupCryptoError)):
        return str(exc)
    if isinstance(exc, OSError):
        if exc.errno == errno.ENOSPC:
            return "Auf dem Sicherungs-Stick ist kein Platz mehr."
        if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
            return "Der Sicherungs-Stick ist nicht beschreibbar."
        return f"Schreibfehler auf dem Sicherungs-Stick: {exc.strerror or exc}"
    return f"Unerwarteter Fehler: {type(exc).__name__}"


class BackupService:
    def __init__(
        self,
        settings: Settings,
        session_factory: SessionFactory,
        events: EventHub,
        *,
        usb_check_seconds: float = 5.0,
        usb_timeout_seconds: float = 30.0,
        usb_copy_timeout_seconds: float = 600.0,
        snapshot_timeout_seconds: float = 600.0,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.events = events
        self.usb_check_seconds = usb_check_seconds
        self.usb_timeout_seconds = usb_timeout_seconds
        self.usb_copy_timeout_seconds = usb_copy_timeout_seconds
        self.snapshot_timeout_seconds = snapshot_timeout_seconds

        backup_dir = settings.data_dir / "backups"
        self.snapshot_dir = backup_dir / "snapshots"
        self.work_dir = backup_dir / "tmp"
        self.keys_dir = settings.data_dir / "keys"
        self.usb_dir = settings.backup_usb_dir
        self.marker = settings.backup_usb_marker
        self.journal = journal.Journal(backup_dir / "journal")

        self.config = BackupSettings()
        self.key: crypto.BackupKey | None = None
        self.usb = _UsbState()
        # Schreiben und Prüfen in getrennten Threads: Eine lange Kopie soll die Erkennung nicht
        # als „Stick reagiert nicht“ erscheinen lassen.
        self._usb_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backup-usb")
        self._probe_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backup-probe")
        self._snapshot_lock = asyncio.Lock()
        self._usb_lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._started_at = _now()
        self._last_snapshot_at: datetime | None = None
        self._last_local: RunOut | None = None
        self._last_usb: RunOut | None = None
        self._latest_dump_size = 0
        self._pg_dump_version: str | None = None
        # Segment -> höchste seq auf dem Stick; None: für diesen Stick/Schlüssel noch unbekannt.
        self._mirrored: dict[str, int] | None = None
        self._journal_pending = 0
        self._journal_error: str | None = None
        # Liegt der neueste lokale Abzug auch auf dem Stick? Sonst wird nachgezogen.
        self._usb_snapshot_current = False
        self._catch_up_not_before = _now()
        self._warning: WarningOut | None = None
        self._published: tuple[Any, ...] | None = None

    # --- Lebenszyklus --------------------------------------------------------------

    async def start(self) -> None:
        global _active
        await asyncio.to_thread(self._prepare_local)
        try:
            async with self.session_factory() as session:
                self.config = await get_setting(session, SETTINGS_KEY, BackupSettings)
                self._last_local = await self._latest_run(session, TARGET_LOCAL)
                self._last_usb = await self._latest_run(session, TARGET_USB)
        except Exception:
            # Die Sicherung soll auch laufen, wenn die Datenbank beim Start klemmt.
            logger.exception(
                "Einstellungen der Sicherung nicht lesbar; es gelten die Standardwerte."
            )
        if self._last_local is not None:
            self._last_snapshot_at = self._last_local.started_at
        self.key = await asyncio.to_thread(crypto.load_key, self.keys_dir)
        # Ohne Blick auf den Stick ist jede lokale Zeile unbestätigt.
        self._journal_pending = await asyncio.to_thread(self.journal.count_after, {})
        await self.check_usb()
        _active = self
        self._task = asyncio.create_task(self._loop(), name="backup-scheduler")

    def _prepare_local(self) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.journal.open()
        latest = self._latest_local_snapshot()
        self._latest_dump_size = latest[0].stat().st_size if latest else 0

    def request_stop(self) -> None:
        """Beendet den Hintergrund-Task (auch aus synchronem Kontext aufrufbar)."""
        global _active
        if _active is self:
            _active = None
        if self._task is not None:
            self._task.cancel()
        self._usb_executor.shutdown(wait=False, cancel_futures=True)
        self._probe_executor.shutdown(wait=False, cancel_futures=True)

    async def stop(self) -> None:
        """Wie `request_stop`, wartet aber, bis der Hintergrund-Task wirklich beendet ist."""
        task = self._task
        self.request_stop()
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def wake(self) -> None:
        self._wake.set()

    async def _loop(self) -> None:
        while True:
            try:
                await self.check_usb()
                if self.usb.present:
                    await self.sync_usb()
                if self.config.enabled and _now() >= self._next_snapshot_due():
                    await self.run_snapshot()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Fehler im Zeitplan der Sicherung.")
            delay = self.usb_check_seconds
            if self.config.enabled:
                until_due = (self._next_snapshot_due() - _now()).total_seconds()
                delay = min(delay, max(until_due, 0.0))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), delay)
            self._wake.clear()

    def _next_snapshot_due(self) -> datetime:
        base = self._last_snapshot_at or self._started_at
        return base + timedelta(minutes=self.config.snapshot_interval_minutes)

    async def _in_usb_thread[T](
        self,
        function: Callable[..., T],
        *args: Any,
        limit_s: float,
        executor: ThreadPoolExecutor | None = None,
    ) -> T:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            executor or self._usb_executor, functools.partial(function, *args)
        )
        return await asyncio.wait_for(future, limit_s)

    # --- Stick ---------------------------------------------------------------------

    async def check_usb(self) -> None:
        try:
            probe = await self._in_usb_thread(
                usb.probe,
                self.usb_dir,
                self.marker,
                limit_s=self.usb_timeout_seconds,
                executor=self._probe_executor,
            )
        except TimeoutError:
            probe = usb.UsbProbe(
                present=self.usb.present,
                writable=False,
                free_bytes=None,
                error="Der Sicherungs-Stick reagiert nicht.",
            )
        was_present = self.usb.present
        self.usb.present = probe.present
        self.usb.writable = probe.writable
        self.usb.free_bytes = probe.free_bytes
        self.usb.error = probe.error
        if probe.present:
            self.usb.last_seen_at = _now()
            if not was_present:
                logger.info("Sicherungs-Stick erkannt.")
        else:
            if was_present:
                logger.warning("Sicherungs-Stick nicht mehr vorhanden.")
            self._mirrored = None
            self._usb_snapshot_current = False
        self._refresh_status()

    def _usb_required_bytes(self) -> int:
        return self._latest_dump_size + USB_RESERVE_BYTES

    def _usb_key(self) -> crypto.BackupKey | None:
        return self.key if self.config.encrypt else None

    def _usb_block_reason(self) -> str | None:
        """Warum gerade nichts auf den Stick geschrieben werden kann (oder None)."""
        if not self.config.usb_enabled:
            return "Die Kopie auf den Stick ist abgeschaltet."
        if not self.usb.present:
            return "Kein Sicherungs-Stick gefunden."
        if not self.usb.writable:
            return "Der Sicherungs-Stick ist nicht beschreibbar."
        if self.config.encrypt and self.key is None:
            return "Das Sicherungspasswort fehlt; ohne Passwort wird nichts auf den Stick kopiert."
        return None

    async def sync_usb(self) -> None:
        """Zieht Mitschrift und neuesten Abzug auf den Stick nach, falls etwas fehlt."""
        if self._journal_pending > 0 or self._mirrored is None:
            await self.sync_journal()
        if not self._usb_snapshot_current and _now() >= self._catch_up_not_before:
            await self._catch_up_snapshot()

    async def initialize_usb(self) -> BackupStatusOut:
        try:
            await self._in_usb_thread(
                usb.initialize, self.usb_dir, self.marker, limit_s=self.usb_timeout_seconds
            )
        except FileExistsError:
            raise ConflictError(
                "Dieser Stick ist bereits als Sicherungs-Stick eingerichtet."
            ) from None
        except (usb.UsbUnavailableError, OSError, TimeoutError) as exc:
            raise ConflictError(_usb_error_message(exc)) from exc
        await self.check_usb()
        await self.sync_usb()
        return self.status()

    async def recheck_usb(self) -> BackupStatusOut:
        await self.check_usb()
        if self.usb.present:
            self._catch_up_not_before = _now()
            await self.sync_usb()
        return self.status()

    # --- Mitschrift ----------------------------------------------------------------

    async def append_journal(self, record: dict[str, Any]) -> int:
        seq = await asyncio.to_thread(self.journal.append, record)
        self._journal_pending += 1
        return seq

    async def sync_journal(self) -> None:
        if self._usb_block_reason() is not None:
            return
        key = self._usb_key()
        started = _now()
        async with self._usb_lock:
            try:
                await self._in_usb_thread(
                    self._sync_journal_files, key, limit_s=self.usb_timeout_seconds
                )
                self._journal_error = None
            except (
                TimeoutError,
                OSError,
                usb.UsbUnavailableError,
                crypto.BackupCryptoError,
            ) as exc:
                self._journal_error = _usb_error_message(exc)
                logger.warning("Mitschrift nicht auf den Stick übertragen: %s", self._journal_error)
                await self._record(
                    started_at=started,
                    kind=KIND_JOURNAL,
                    target=TARGET_USB,
                    ok=False,
                    error=self._journal_error,
                )
            self._journal_pending = await asyncio.to_thread(
                self.journal.count_after, dict(self._mirrored or {})
            )
        self._refresh_status()

    def _sync_journal_files(self, key: crypto.BackupKey | None) -> None:
        directory = usb.ensure_dir(self.usb_dir, self.marker, usb.JOURNAL_DIR)
        if self._mirrored is None:
            self._mirrored = {}
        mirrored = self._mirrored
        for segment, last_seq in sorted(self.journal.segment_last_seq().items()):
            usb_path = directory / journal.usb_file_name(segment, key)
            if segment not in mirrored:
                on_stick = journal.read_usb_file(usb_path, key)
                mirrored[segment] = max((entry.seq for entry in on_stick), default=0)
            if last_seq <= mirrored[segment]:
                continue
            missing = [
                entry
                for entry in journal.read_entries(self.journal.directory / segment)
                if entry.seq > mirrored[segment]
            ]
            usb.require_marker(self.usb_dir, self.marker)
            journal.append_usb_file(usb_path, missing, key)
            mirrored[segment] = max(entry.seq for entry in missing)

    # --- Abzüge --------------------------------------------------------------------

    async def run_snapshot(self) -> list[RunOut]:
        """Abzug lokal, dann Kopie auf den Stick. Liefert die protokollierten Läufe."""
        async with self._snapshot_lock:
            started = _now()
            self._last_snapshot_at = started
            local = await self._snapshot_local(started)
            self._last_local = local
            self._announce(local)
            runs = [local]
            if local.ok and local.file_name is not None and local.sha256 is not None:
                await asyncio.to_thread(self._rotate_local)
                if self.config.usb_enabled:
                    runs.append(
                        await self._copy_to_usb(self.snapshot_dir / local.file_name, local.sha256)
                    )
            self._refresh_status()
            return runs

    async def _snapshot_local(self, started: datetime) -> RunOut:
        name = f"{SNAPSHOT_PREFIX}{started:%Y%m%dT%H%M%S%f}Z{LOCAL_SUFFIX}"
        path = self.snapshot_dir / name
        tmp = path.with_name(path.name + fsutil.TMP_SUFFIX)
        try:
            await pgtools.dump(
                pgtools.PgTarget.from_url(self.settings.database_url),
                tmp,
                self.snapshot_timeout_seconds,
            )
            digest, size = await asyncio.to_thread(self._finalize_local, tmp, path)
        except (pgtools.PgToolError, OSError) as exc:
            message = str(exc) if isinstance(exc, pgtools.PgToolError) else f"Schreibfehler: {exc}"
            logger.error("Sicherung fehlgeschlagen: %s", message)
            return await self._record(
                started_at=started, kind=KIND_SNAPSHOT, target=TARGET_LOCAL, ok=False, error=message
            )
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()
        self._latest_dump_size = size
        return await self._record(
            started_at=started,
            kind=KIND_SNAPSHOT,
            target=TARGET_LOCAL,
            ok=True,
            file_name=name,
            size_bytes=size,
            sha256=digest,
        )

    @staticmethod
    def _finalize_local(tmp: Path, path: Path) -> tuple[str, int]:
        with tmp.open("rb+") as file:
            os.fsync(file.fileno())
        digest = fsutil.sha256_file(tmp)
        size = tmp.stat().st_size
        os.replace(tmp, path)
        fsutil.fsync_dir(path.parent)
        fsutil.write_checksum(path, digest)
        return digest, size

    def _latest_local_snapshot(self) -> tuple[Path, str] | None:
        for path in sorted(
            self.snapshot_dir.glob(f"{SNAPSHOT_PREFIX}*{LOCAL_SUFFIX}"), reverse=True
        ):
            digest = fsutil.read_checksum(path)
            if digest is not None:
                return path, digest
        return None

    def _rotate_local(self) -> None:
        _rotate(self.snapshot_dir, LOCAL_SUFFIX, self.config.keep_local)

    def _rotate_usb(self) -> None:
        directory = self.usb_dir / usb.SNAPSHOT_DIR
        usb.require_marker(self.usb_dir, self.marker)
        for suffix in (USB_ENCRYPTED_SUFFIX, USB_PLAIN_SUFFIX):
            _rotate(directory, suffix, self.config.keep_usb)

    async def _manifest(self, dump: Path, digest: str) -> dict[str, Any]:
        if self._pg_dump_version is None:
            self._pg_dump_version = await pgtools.tool_version("pg_dump")
        return archive.build_manifest(
            created_at=_now().isoformat(),
            app_version=__version__,
            pg_dump_version=self._pg_dump_version,
            dump=dump,
            dump_sha256=digest,
            keys_dir=self.keys_dir,
        )

    async def _copy_to_usb(self, dump: Path, digest: str) -> RunOut:
        started = _now()
        reason = self._usb_block_reason()
        free = self.usb.free_bytes
        if reason is None and free is not None and free < self._usb_required_bytes():
            reason = "Auf dem Sicherungs-Stick ist nicht genug Platz für die Sicherung."
        if reason is not None:
            run = await self._record(
                started_at=started, kind=KIND_SNAPSHOT, target=TARGET_USB, ok=False, error=reason
            )
            self._last_usb = run
            self._usb_snapshot_current = False
            return run
        key = self._usb_key()
        try:
            manifest = await self._manifest(dump, digest)
            async with self._usb_lock:
                name, size, usb_digest = await self._in_usb_thread(
                    self._write_usb_snapshot,
                    dump,
                    manifest,
                    key,
                    limit_s=self.usb_copy_timeout_seconds,
                )
                await self._in_usb_thread(self._rotate_usb, limit_s=self.usb_timeout_seconds)
        except pgtools.PgToolError as exc:
            run = await self._record(
                started_at=started, kind=KIND_SNAPSHOT, target=TARGET_USB, ok=False, error=str(exc)
            )
        except (TimeoutError, OSError, usb.UsbUnavailableError) as exc:
            message = _usb_error_message(exc)
            logger.warning("Kopie auf den Stick fehlgeschlagen: %s", message)
            run = await self._record(
                started_at=started, kind=KIND_SNAPSHOT, target=TARGET_USB, ok=False, error=message
            )
        else:
            run = await self._record(
                started_at=started,
                kind=KIND_SNAPSHOT,
                target=TARGET_USB,
                ok=True,
                file_name=name,
                size_bytes=size,
                sha256=usb_digest,
            )
        self._last_usb = run
        self._usb_snapshot_current = run.ok
        if not run.ok:
            # Nicht alle paar Sekunden erneut versuchen, sondern im Takt der Sicherung.
            self._catch_up_not_before = _now() + timedelta(
                minutes=self.config.snapshot_interval_minutes
            )
        self._announce(run)
        return run

    def _write_usb_snapshot(
        self, dump: Path, manifest: dict[str, Any], key: crypto.BackupKey | None
    ) -> tuple[str, int, str]:
        directory = usb.ensure_dir(self.usb_dir, self.marker, usb.SNAPSHOT_DIR)
        stem = dump.name.removesuffix(LOCAL_SUFFIX)
        path = directory / (stem + (USB_ENCRYPTED_SUFFIX if key is not None else USB_PLAIN_SUFFIX))
        hashing: list[fsutil.HashingWriter] = []

        def produce(file: Any) -> None:
            writer = fsutil.HashingWriter(file)
            hashing.append(writer)
            write_backup_file(writer, manifest, dump, self.keys_dir, key)

        usb.require_marker(self.usb_dir, self.marker)
        fsutil.atomic_write(path, produce, mode=0o600)
        digest = hashing[0].hexdigest()
        fsutil.write_checksum(path, digest)
        # Zurücklesen vom Datenträger (Seitencache verworfen) und vergleichen.
        if fsutil.sha256_file(path, uncached=True) != digest:
            path.unlink(missing_ok=True)
            fsutil.checksum_path(path).unlink(missing_ok=True)
            raise OSError(errno.EIO, "Die Kopie auf dem Stick weicht nach dem Zurücklesen ab.")
        return path.name, hashing[0].size, digest

    def _usb_has_snapshot(self, stem: str, key: crypto.BackupKey | None) -> bool:
        suffix = USB_ENCRYPTED_SUFFIX if key is not None else USB_PLAIN_SUFFIX
        path = self.usb_dir / usb.SNAPSHOT_DIR / (stem + suffix)
        if not path.is_file() or fsutil.read_checksum(path) is None:
            return False
        # Mit einem anderen Schlüssel verschlüsselt? Dann zählt die Kopie nicht als aktuell.
        if key is not None:
            with path.open("rb") as file:
                return crypto.read_key_header(file) == key.key_header
        return True

    async def _catch_up_snapshot(self) -> None:
        if self._usb_block_reason() is not None:
            return
        async with self._snapshot_lock:
            latest = await asyncio.to_thread(self._latest_local_snapshot)
            if latest is None:
                self._usb_snapshot_current = True
                return
            dump, digest = latest
            stem = dump.name.removesuffix(LOCAL_SUFFIX)
            try:
                present = await self._in_usb_thread(
                    self._usb_has_snapshot, stem, self._usb_key(), limit_s=self.usb_timeout_seconds
                )
            except (TimeoutError, OSError, crypto.BackupCryptoError) as exc:
                logger.warning("Stick nicht lesbar: %s", _usb_error_message(exc))
                return
            if present:
                self._usb_snapshot_current = True
                return
            logger.info("Neuester Abzug fehlt auf dem Stick, wird nachgezogen: %s", dump.name)
            await self._copy_to_usb(dump, digest)
        self._refresh_status()

    # --- Protokoll und Status ---------------------------------------------------------

    async def _record(self, **fields: Any) -> RunOut:
        run = BackupRun(id=uuid.uuid4(), finished_at=_now(), **fields)
        try:
            async with self.session_factory() as session, session.begin():
                session.add(run)
        except Exception:
            logger.exception("Sicherungslauf konnte nicht protokolliert werden.")
        return RunOut.model_validate(
            {
                "file_name": None,
                "size_bytes": None,
                "sha256": None,
                "error": None,
                **fields,
                "id": run.id,
                "finished_at": run.finished_at,
            }
        )

    @staticmethod
    async def _latest_run(session: Any, target: str) -> RunOut | None:
        run = await session.scalar(
            select(BackupRun)
            .where(BackupRun.kind == KIND_SNAPSHOT, BackupRun.target == target)
            .order_by(BackupRun.started_at.desc())
            .limit(1)
        )
        return None if run is None else RunOut.model_validate(run, from_attributes=True)

    def _announce(self, run: RunOut) -> None:
        payload = {"run": run.model_dump(mode="json")}
        self.events.publish(EVENT_COMPLETED if run.ok else EVENT_FAILED, payload)

    def _current_warning(self) -> tuple[str, str] | None:
        if not self.config.enabled:
            return "backup_disabled", "Die automatische Sicherung ist abgeschaltet."
        if self._last_local is not None and not self._last_local.ok:
            return (
                "snapshot_failed",
                f"Die letzte Sicherung ist fehlgeschlagen: {self._last_local.error}",
            )
        if not self.config.usb_enabled:
            return None
        if not self.usb.present:
            return (
                "usb_missing",
                "Kein Sicherungs-Stick gefunden. Bitte den Stick einstecken – bis dahin liegen "
                "die Sicherungen nur auf dem Server.",
            )
        if not self.usb.writable:
            detail = f" ({self.usb.error})" if self.usb.error else ""
            return "usb_not_writable", f"Der Sicherungs-Stick ist nicht beschreibbar{detail}."
        if self.usb.free_bytes is not None and self.usb.free_bytes < self._usb_required_bytes():
            return "usb_full", "Auf dem Sicherungs-Stick ist nicht mehr genug Platz."
        if self.config.encrypt and self.key is None:
            return (
                "passphrase_missing",
                "Das Sicherungspasswort fehlt. Bis es gesetzt ist, wird nichts auf den Stick "
                "kopiert.",
            )
        if self._last_usb is not None and not self._last_usb.ok:
            return (
                "usb_copy_failed",
                f"Die letzte Kopie auf den Stick ist fehlgeschlagen: {self._last_usb.error}",
            )
        if self._journal_error is not None:
            return (
                "journal_sync_failed",
                f"Die Mitschrift kam nicht auf den Stick: {self._journal_error}",
            )
        return None

    def _refresh_status(self) -> None:
        current = self._current_warning()
        if current is None:
            self._warning = None
        elif self._warning is None or self._warning.code != current[0]:
            self._warning = WarningOut(code=current[0], message_de=current[1], since=_now())
        else:
            self._warning = self._warning.model_copy(update={"message_de": current[1]})
        signature = (
            self.usb.present,
            self.usb.writable,
            self._warning.code if self._warning else None,
            self.key is not None,
        )
        if signature != self._published:
            self._published = signature
            self.events.publish(EVENT_STATUS, self.status().model_dump(mode="json"))

    def status(self) -> BackupStatusOut:
        return BackupStatusOut(
            usb=UsbStatusOut(
                present=self.usb.present,
                writable=self.usb.writable,
                free_bytes=self.usb.free_bytes,
                last_seen_at=self.usb.last_seen_at,
            ),
            last_snapshot=self._last_local,
            last_usb_copy=self._last_usb,
            journal=JournalStatusOut(pending=self._journal_pending),
            warning=self._warning,
            passphrase_set=self.key is not None,
        )

    # --- Einstellungen und Passwort -----------------------------------------------------

    async def update_config(self, config: BackupSettings) -> BackupSettings:
        async with self.session_factory() as session, session.begin():
            await put_setting(session, SETTINGS_KEY, config)
        previous, self.config = self.config, config
        if previous.encrypt != config.encrypt or (config.usb_enabled and not previous.usb_enabled):
            self._mirrored = None
            self._usb_snapshot_current = False
            self._catch_up_not_before = _now()
        self._refresh_status()
        self.wake()
        return config

    async def set_passphrase(self, passphrase: str, current: str | None) -> PassphraseOut:
        if self.key is not None:
            if current is None:
                raise ConflictError(
                    "Es ist bereits ein Sicherungspasswort gesetzt. Zum Ändern bitte das "
                    "bisherige Passwort mit angeben."
                )
            try:
                await asyncio.to_thread(crypto.unwrap_key, self.key.key_header, current)
            except crypto.WrongPassphraseError:
                raise BackupError("Das bisherige Sicherungspasswort stimmt nicht.") from None
        key = await asyncio.to_thread(crypto.create_key, passphrase)
        async with self._usb_lock:
            await asyncio.to_thread(crypto.save_key, self.keys_dir, key)
            self.key = key
            self._mirrored = None
            self._usb_snapshot_current = False
            self._catch_up_not_before = _now()
        logger.info("Sicherungspasswort gesetzt (Schlüssel %s).", key.key_id)
        self._refresh_status()
        self.wake()
        return PassphraseOut(passphrase_set=True, key_id=key.key_id)

    # --- Läufe, Download, Prüfung ------------------------------------------------------

    async def list_runs(
        self, session: Any, limit: int, kind: str | None, target: str | None
    ) -> list[RunOut]:
        statement = select(BackupRun).order_by(BackupRun.started_at.desc()).limit(limit)
        if kind is not None:
            statement = statement.where(BackupRun.kind == kind)
        if target is not None:
            statement = statement.where(BackupRun.target == target)
        runs = (await session.scalars(statement)).all()
        return [RunOut.model_validate(run, from_attributes=True) for run in runs]

    async def _snapshot_run(self, session: Any, run_id: uuid.UUID) -> BackupRun:
        run = await session.get(BackupRun, run_id)
        if run is None:
            raise NotFoundError("Diesen Sicherungslauf gibt es nicht.")
        if run.kind != KIND_SNAPSHOT or not run.ok or run.file_name is None:
            raise ConflictError("Das geht nur mit einem erfolgreichen Datenbank-Abzug.")
        return run

    async def build_download(self, session: Any, run_id: uuid.UUID) -> tuple[Path, str]:
        """Verschlüsselt einen lokalen Abzug samt Schlüsseln in eine temporäre Datei."""
        run = await self._snapshot_run(session, run_id)
        if run.target != TARGET_LOCAL:
            raise ConflictError(
                "Herunterladen lässt sich nur ein Abzug vom Server, nicht vom Stick."
            )
        dump = self.snapshot_dir / run.file_name
        if not dump.is_file():
            raise NotFoundError("Dieser Abzug wurde inzwischen durch neuere Sicherungen ersetzt.")
        if self.key is None:
            raise ConflictError(
                "Zum Herunterladen muss zuerst ein Sicherungspasswort gesetzt werden."
            )
        if await asyncio.to_thread(fsutil.sha256_file, dump) != run.sha256:
            raise ConflictError("Der Abzug auf dem Server ist beschädigt (Prüfsumme weicht ab).")
        manifest = await self._manifest(dump, run.sha256)
        out = self.work_dir / f"download-{uuid.uuid4().hex}{USB_ENCRYPTED_SUFFIX}"
        key = self.key

        def produce() -> None:
            with out.open("wb") as file:
                write_backup_file(file, manifest, dump, self.keys_dir, key)

        try:
            await asyncio.to_thread(produce)
        except BaseException:
            out.unlink(missing_ok=True)
            raise
        return out, "schiesshub-" + dump.name.removesuffix(LOCAL_SUFFIX) + USB_ENCRYPTED_SUFFIX

    async def verify(self, session: Any, run_id: uuid.UUID, passphrase: str | None) -> VerifyOut:
        """Prüft eine Sicherung: lesbar, Prüfsumme, Inhalt. Spielt nichts zurück."""
        run = await self._snapshot_run(session, run_id)
        if run.target == TARGET_LOCAL:
            path = self.snapshot_dir / run.file_name
            if not path.is_file():
                raise NotFoundError(
                    "Dieser Abzug wurde inzwischen durch neuere Sicherungen ersetzt."
                )
            checksum_ok = await asyncio.to_thread(fsutil.sha256_file, path) == run.sha256
            toc, error = await _toc(path)
            return VerifyOut(
                ok=checksum_ok and error is None,
                file_name=path.name,
                location="local",
                encrypted=False,
                size_bytes=path.stat().st_size,
                checksum_ok=checksum_ok,
                entries=[path.name],
                database_toc_entries=toc,
                manifest=None,
                error=error if checksum_ok else "Die Prüfsumme des Abzugs weicht ab.",
            )
        if not self.usb.present:
            raise ConflictError("Der Stick mit dieser Sicherung steckt nicht.")
        path = self.usb_dir / usb.SNAPSHOT_DIR / run.file_name
        encrypted = path.suffix == USB_ENCRYPTED_SUFFIX
        if encrypted and passphrase is None:
            raise BackupError("Zum Prüfen bitte das Sicherungspasswort angeben.")
        work = Path(tempfile.mkdtemp(prefix="verify-", dir=self.work_dir))
        try:
            try:
                size, checksum_ok, contents = await self._in_usb_thread(
                    _open_backup, path, passphrase, work, limit_s=self.usb_copy_timeout_seconds
                )
            except FileNotFoundError:
                raise NotFoundError("Diese Sicherung liegt nicht mehr auf dem Stick.") from None
            except crypto.WrongPassphraseError as exc:
                raise BackupError(str(exc)) from None
            except (crypto.BackupCryptoError, archive.ArchiveError, OSError, TimeoutError) as exc:
                message = (
                    str(exc)
                    if isinstance(exc, (crypto.BackupCryptoError, archive.ArchiveError))
                    else _usb_error_message(exc)
                )
                return VerifyOut(
                    ok=False,
                    file_name=path.name,
                    location="usb",
                    encrypted=encrypted,
                    size_bytes=0,
                    checksum_ok=False,
                    entries=[],
                    database_toc_entries=None,
                    manifest=None,
                    error=message,
                )
            toc, error = (None, None)
            if contents.database_file is not None:
                toc, error = await _toc(contents.database_file)
            if not contents.database_sha256_ok:
                error = "Die Prüfsumme des Datenbank-Abzugs im Archiv weicht ab."
            elif not checksum_ok:
                error = "Die Prüfsumme der Datei auf dem Stick weicht ab."
            return VerifyOut(
                ok=error is None,
                file_name=path.name,
                location="usb",
                encrypted=encrypted,
                size_bytes=size,
                checksum_ok=checksum_ok and contents.database_sha256_ok,
                entries=contents.entries,
                database_toc_entries=toc,
                manifest=contents.manifest,
                error=error,
            )
        finally:
            await asyncio.to_thread(shutil.rmtree, work, True)


# --- Gemeinsame Bausteine (auch für die Wiederherstellung) -----------------------------


def write_backup_file(
    out: Any,
    manifest: dict[str, Any],
    dump: Path,
    keys_dir: Path,
    key: crypto.BackupKey | None,
) -> None:
    """Schreibt das Sicherungsarchiv nach `out`, mit `key` verschlüsselt."""
    if key is None:
        archive.write_archive(out, manifest, dump, keys_dir)
        return
    writer = crypto.EncryptingWriter(out, key)
    archive.write_archive(writer, manifest, dump, keys_dir)
    writer.close()


def _open_backup(
    path: Path, passphrase: str | None, target_dir: Path | None
) -> tuple[int, bool, archive.ArchiveContents]:
    """Prüfsumme der Datei und Inhalt des Archivs (verschlüsselt `.shb` oder `.tar`)."""
    expected = fsutil.read_checksum(path)
    checksum_ok = expected is not None and fsutil.sha256_file(path) == expected
    with path.open("rb") as file:
        if path.suffix == USB_ENCRYPTED_SUFFIX:
            if passphrase is None:
                raise crypto.WrongPassphraseError()
            reader = crypto.DecryptingReader(file, passphrase=passphrase)
            contents = archive.read_archive(reader, target_dir)
            reader.finish()
        else:
            contents = archive.read_archive(file, target_dir)
    return path.stat().st_size, checksum_ok, contents


async def _toc(dump: Path) -> tuple[int | None, str | None]:
    try:
        return len(await pgtools.list_contents(dump)), None
    except pgtools.PgToolError as exc:
        return None, str(exc)


def _rotate(directory: Path, suffix: str, keep: int) -> None:
    """Behält die neuesten `keep` Sicherungen; löscht ältere samt Prüfsumme und Reste."""
    if not directory.is_dir():
        return
    for leftover in directory.glob(f"{SNAPSHOT_PREFIX}*{suffix}{fsutil.TMP_SUFFIX}"):
        leftover.unlink(missing_ok=True)
    files = sorted(directory.glob(f"{SNAPSHOT_PREFIX}*{suffix}"), reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)
        fsutil.checksum_path(old).unlink(missing_ok=True)


# --- Einbindung in die Anwendung --------------------------------------------------------


async def on_startup(app: FastAPI) -> None:
    service = BackupService(app.state.settings, app.state.session_factory, app.state.events)
    app.state.backup = service
    await service.start()


async def on_shutdown(app: FastAPI) -> None:
    """Beendet den Hintergrund-Task, bevor der Kern die Datenbankverbindung schließt."""
    service: BackupService | None = getattr(app.state, "backup", None)
    if service is not None:
        await service.stop()
