"""Geführte Wiederherstellung in der App (nur Administrator mit PIN).

Ablauf von `execute` (Hintergrundauftrag, Fortschritt unter `GET /backup/restore/status`):

1. check        Sicherung lesen (Prüfsumme, entschlüsseln), Schema-Stand, Schlüssel, Rechte des
                Datenbank-Benutzers, Zugang der auslösenden Person.
2. maintenance  Wartungszustand (`maintenance`): schreibende Anfragen bekommen 503; begonnene
                Eingaben werden abgewartet.
3. pre_backup   Sicherung des jetzigen Stands („vor Wiederherstellung“), Kopie nach
                `DATA_DIR/backups/pre-restore`. Schlägt sie fehl: Abbruch.
4. load         Abzug in eine neue Datenbank `<name>_restore_<Zeit>` einspielen (pg_restore, eine
                Transaktion). Die laufende Datenbank bleibt unberührt.
5. upgrade      Ist die Sicherung älter als die laufende Datenbank: `alembic upgrade` der neuen
                Datenbank genau auf deren Stand. Neuere Sicherungen lehnt schon `check` ab.
6. journal      Mitschrift nachtragen (`journal_apply`), wie auf der Konsole.
7. verify       Neue Datenbank prüfen (Schema-Stand, Systemrolle, Namen entschlüsselbar) und
                Server-Einstellungen übernehmen (Sicherung; eine eingeschaltete
                Berechtigungsprüfung wird nie durch eine Wiederherstellung ausgeschaltet).
8. swap         Lesende Anfragen kurz anhalten, Module anhalten, fehlende Schlüssel schreiben,
                Verbindungen schließen, `ALTER DATABASE … RENAME` (alt →
                `<name>_pre_restore_<Zeit>`, neu → `<name>`), Verbindungspool neu aufbauen,
                Module neu starten.
9. finish       Audit-Eintrag `backup.restored`, Sicherung des neuen Stands, Wartung beenden.

Schlägt ein Schritt vor dem Tausch fehl, wird die neue Datenbank gelöscht; die laufende ist
unverändert. Die alte Datenbank wird nach dem Tausch nie gelöscht, ihr Name steht im Ergebnis.

Das Sicherungspasswort wird weder gespeichert noch protokolliert; es lebt nur im Speicher des
laufenden Auftrags.
"""

import asyncio
import contextlib
import functools
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
from fastapi import FastAPI
from sqlalchemy import func, make_url, select, text
from sqlalchemy.dialects.postgresql import insert

from app import __version__
from app.core import crypto as field_crypto
from app.core.db import create_engine, create_session_factory
from app.core.security import Actor
from app.core.settings_store import Setting
from app.modules.backup import (
    archive,
    crypto,
    dumpinfo,
    fsutil,
    journal,
    journal_apply,
    pgtools,
    usb,
)
from app.modules.backup.maintenance import EVENT_RESTORE, MaintenanceState
from app.modules.backup.models import BackupRun
from app.modules.backup.schemas import (
    SETTINGS_KEY,
    AccessCheckOut,
    ComparisonOut,
    JournalReportOut,
    KeysCheckOut,
    RestoreExecuteIn,
    RestorePreviewIn,
    RestorePreviewOut,
    RestoreResultOut,
    RestoreSourceOut,
    RestoreSourcesOut,
    RestoreStatusOut,
    RestoreStepOut,
    RunOut,
    SchemaCheckOut,
    TournamentPreviewOut,
)
from app.modules.backup.service import (
    LOCAL_SUFFIX,
    USB_ENCRYPTED_SUFFIX,
    USB_PLAIN_SUFFIX,
    BackupError,
    BackupService,
    ConflictError,
    NotFoundError,
    _open_backup,
)

logger = logging.getLogger("schiesshub.backup")

PRE_RESTORE_DIR = "pre-restore"
BACKEND_DIR = Path(__file__).resolve().parents[3]
# Gespeicherter Schalter der Berechtigungsprüfung (Modul auth). Eine Wiederherstellung darf ihn
# nie ausschalten: Ausschalten geht nur auf der Server-Konsole.
AUTH_ENFORCEMENT_KEY = "auth_enforcement"
FIELD_KEYS = field_crypto.KEY_FILE_NAME
BACKUP_KEY = crypto.KEY_FILE_NAME
DRAIN_WRITES_S = 30.0
DRAIN_READS_S = 10.0
RESTORE_TIMEOUT_S = 3600.0
MIGRATION_TIMEOUT_S = 900.0
RENAME_ATTEMPTS = 40
MAX_IDENTIFIER = 63

_NAME = re.compile(r"^snapshot-(\d{8}T\d{6})(\d{0,6})Z\.(shb|tar|dump)$")
_SUFFIXES = {
    "usb": (USB_ENCRYPTED_SUFFIX, USB_PLAIN_SUFFIX),
    "local": (LOCAL_SUFFIX,),
    "pre_restore": (LOCAL_SUFFIX,),
}

STEPS: list[tuple[str, str]] = [
    ("check", "Sicherung prüfen"),
    ("maintenance", "Eingaben anhalten"),
    ("pre_backup", "Jetzigen Stand sichern"),
    ("load", "In neue Datenbank einspielen"),
    ("upgrade", "Datenbank auf den Stand der App bringen"),
    ("journal", "Mitschrift nachtragen"),
    ("verify", "Neue Datenbank prüfen"),
    ("swap", "Datenbank tauschen"),
    ("finish", "Abschließen"),
]
LABELS = dict(STEPS)

CONSOLE_HINT = (
    "Notzugang über die Server-Konsole: `python -m app.modules.auth.cli ensure-admin NAME` "
    "(Administrator mit neuer PIN) und `python -m app.modules.auth.cli pairing-code` (Gerät "
    "koppeln)."
)


class RestoreFailed(Exception):
    """Abbruch mit einer Meldung für Anwender. Die laufende Datenbank ist unverändert."""


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _derived_name(base: str, suffix: str) -> str:
    """`<base><suffix>`, höchstens 63 Bytes (sonst kürzt PostgreSQL still)."""
    room = MAX_IDENTIFIER - len(suffix.encode())
    encoded = base.encode()[:room]
    return encoded.decode(errors="ignore") + suffix


def _is_true(value: str | None) -> bool:
    return value in ("t", "true", "True", "1")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    if re.search(r"[+-]\d\d$", value):
        value += ":00"
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# --- Quellen --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Source:
    location: str
    path: Path
    created_at: datetime

    @property
    def id(self) -> str:
        return f"{self.location}:{self.path.name}"

    @property
    def encrypted(self) -> bool:
        return self.path.suffix == USB_ENCRYPTED_SUFFIX

    @property
    def contains_keys(self) -> bool:
        return self.path.suffix != LOCAL_SUFFIX


def _created_at(name: str) -> datetime | None:
    match = _NAME.match(name)
    if match is None:
        return None
    moment = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    fraction = match.group(2)
    return moment.replace(microsecond=int(fraction.ljust(6, "0"))) if fraction else moment


def _scan(directory: Path, location: str) -> list[Source]:
    if not directory.is_dir():
        return []
    sources = []
    for path in directory.iterdir():
        created = _created_at(path.name)
        if created is not None and path.suffix in _SUFFIXES[location] and path.is_file():
            sources.append(Source(location, path, created))
    return sources


def _journal_days(directories: list[Path]) -> set[str]:
    days: set[str] = set()
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in directory.glob(f"{journal.SEGMENT_PREFIX}*"):
            day = path.name.removeprefix(journal.SEGMENT_PREFIX)[:10]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                days.add(day)
    return days


# --- Schema-Stand ---------------------------------------------------------------------


@functools.cache
def _script() -> Any:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))


def _revisions() -> tuple[frozenset[str], tuple[str, ...]]:
    """Bekannte Revisionen und Köpfe der Migrationsdateien dieser App."""
    script = _script()
    known = frozenset(revision.revision for revision in script.walk_revisions())
    return known, tuple(sorted(script.get_heads()))


def _ancestors(revisions: list[str]) -> set[str]:
    """Die Revisionen und alle ihre Vorgänger."""
    if not revisions:
        return set()
    return {revision.revision for revision in _script().iterate_revisions(tuple(revisions), "base")}


async def live_revisions(session_factory: Any) -> list[str]:
    """Migrationsstand der laufenden Datenbank. Daran wird gemessen, nicht an den Dateien:
    Zwischen Start und Wiederherstellung können neue Migrationsdateien hinzukommen."""
    async with session_factory() as session:
        return sorted(await session.scalars(text("SELECT version_num FROM alembic_version")))


def schema_check(revisions: list[str], current: list[str] | None = None) -> SchemaCheckOut:
    """Vergleicht den Stand der Sicherung mit `current` (laufende Datenbank; sonst die Köpfe)."""
    known, heads = _revisions()
    current = sorted(current) if current else list(heads)
    if not revisions:
        return SchemaCheckOut(
            backup=[],
            current=current,
            state="newer",
            message_de="Im Abzug fehlt der Stand der Datenbank-Migrationen; das ist keine "
            "vollständige Schiesshub-Sicherung.",
        )
    unknown = [revision for revision in revisions if revision not in known]
    if unknown:
        return SchemaCheckOut(
            backup=revisions,
            current=current,
            state="newer",
            message_de="Die Sicherung stammt von einer neueren Version der App (Stand "
            + ", ".join(unknown)
            + "). Bitte zuerst die App aktualisieren.",
        )
    if not set(revisions) <= _ancestors(current):
        return SchemaCheckOut(
            backup=revisions,
            current=current,
            state="newer",
            message_de="Die Sicherung hat einen neueren Datenbank-Stand als der laufende Server ("
            + ", ".join(revisions)
            + "). Bitte zuerst den Server aktualisieren und neu starten.",
        )
    if set(revisions) == set(current):
        return SchemaCheckOut(
            backup=revisions,
            current=current,
            state="same",
            message_de="Die Sicherung passt zur laufenden Version der App.",
        )
    return SchemaCheckOut(
        backup=revisions,
        current=current,
        state="older",
        message_de="Die Sicherung stammt von einer älteren Version der App. Nach dem Einspielen "
        "wird die neue Datenbank auf den aktuellen Stand gebracht, bevor sie die laufende ersetzt.",
    )


# --- Schlüssel ------------------------------------------------------------------------


@dataclass(slots=True)
class KeyPlan:
    field_keys: str = "none"
    backup_key: str = "none"
    install: list[str] = field(default_factory=list)
    set_aside: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def message(self) -> str:
        if self.conflicts:
            return (
                "Auf dem Server liegen andere Schlüssel als in der Sicherung ("
                + ", ".join(self.conflicts)
                + "). Die Namen der Sicherung ließen sich mit den Schlüsseln des Servers nicht "
                "lesen, und vorhandene Schlüssel werden nie überschrieben. Bitte über die Konsole "
                "wiederherstellen (docs/WIEDERHERSTELLUNG.md)."
            )
        parts = {
            "same": "Der Namensschlüssel ist derselbe wie auf dem Server.",
            "compatible": "Der Namensschlüssel des Servers enthält den der Sicherung; er bleibt.",
            "install": "Der Namensschlüssel kommt aus der Sicherung auf den Server.",
            "replace_unused": "Der Namensschlüssel des Servers ist noch unbenutzt (keine "
            "Personen). Er wird beiseitegelegt, der aus der Sicherung wird verwendet.",
            "none": "Die Sicherung enthält keine Schlüssel; es gelten die des Servers.",
        }
        text_parts = [parts[self.field_keys]]
        if self.backup_key == "keep_current":
            text_parts.append("Das heutige Sicherungspasswort gilt weiter.")
        elif self.backup_key == "install":
            text_parts.append("Das Sicherungspasswort der Sicherung wird übernommen.")
        return " ".join(text_parts)

    def out(self) -> KeysCheckOut:
        return KeysCheckOut(
            field_keys="conflict" if self.conflicts else self.field_keys,  # type: ignore[arg-type]
            backup_key=self.backup_key,  # type: ignore[arg-type]
            message_de=self.message(),
        )


def _key_files(directory: Path) -> Iterator[Path]:
    for path in sorted(directory.rglob("*")):
        if path.is_file() and not path.name.endswith(fsutil.TMP_SUFFIX):
            yield path


def plan_keys(source: Path | None, keys_dir: Path, live_persons: int) -> KeyPlan:
    """Wie die Schlüssel der Sicherung zu denen des Servers passen (Regeln wie `restore.py`).

    Fehlende werden geschrieben, gleiche bleiben, abweichende werden nie überschrieben. Zwei
    Ausnahmen, die nichts zerstören: Ein Namensschlüssel des Servers, der alle Schlüssel der
    Sicherung enthält (Schlüsselwechsel nach der Sicherung), bleibt einfach; ein unbenutzter
    (keine Personen im jetzigen Stand) wird umbenannt statt überschrieben. Ein abweichender
    Sicherungsschlüssel heißt nur, dass das Passwort inzwischen geändert wurde: Der heutige bleibt.
    """
    plan = KeyPlan()
    if source is None or not source.is_dir():
        return plan
    for path in _key_files(source):
        relative = path.relative_to(source).as_posix()
        target = keys_dir / relative
        exists = target.is_file()
        same = exists and target.read_bytes() == path.read_bytes()
        if relative == FIELD_KEYS:
            if not exists:
                plan.field_keys = "install"
                plan.install.append(relative)
            elif same:
                plan.field_keys = "same"
            elif _ring_contains(keys_dir, source):
                plan.field_keys = "compatible"
            elif live_persons == 0:
                plan.field_keys = "replace_unused"
                plan.set_aside.append(relative)
                plan.install.append(relative)
            else:
                plan.field_keys = "conflict"
                plan.conflicts.append(relative)
        elif relative == BACKUP_KEY:
            if not exists:
                plan.backup_key = "install"
                plan.install.append(relative)
            else:
                plan.backup_key = "same" if same else "keep_current"
        elif not exists:
            plan.install.append(relative)
        elif not same:
            plan.conflicts.append(relative)
    return plan


def _ring_contains(current_dir: Path, source_dir: Path) -> bool:
    try:
        current = field_crypto.load_keyring(current_dir, create=False)
        backup = field_crypto.load_keyring(source_dir, create=False)
    except field_crypto.CryptoError:
        return False
    return all(current.keys.get(key_id) == key for key_id, key in backup.keys.items())


def apply_keys(plan: KeyPlan, source: Path, keys_dir: Path, stamp: str) -> list[tuple[Path, Path]]:
    """Legt Unbenutztes beiseite und schreibt fehlende Schlüssel; liefert, was umbenannt wurde."""
    moved: list[tuple[Path, Path]] = []
    keys_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(keys_dir, 0o700)
    for relative in plan.set_aside:
        target = keys_dir / relative
        aside = target.with_name(f"{target.name}.unused-{stamp}")
        os.replace(target, aside)
        moved.append((target, aside))
    for relative in plan.install:
        target = keys_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fsutil.atomic_write_bytes(target, (source / relative).read_bytes(), mode=0o600)
    return moved


def undo_keys(plan: KeyPlan, keys_dir: Path, moved: list[tuple[Path, Path]]) -> None:
    for relative in plan.install:
        (keys_dir / relative).unlink(missing_ok=True)
    for target, aside in moved:
        os.replace(aside, target)


# --- Status ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Job:
    source: RestoreSourceOut
    actor: Actor
    passphrase: str | None = field(repr=False)
    apply_journal: bool
    accept_lockout: bool
    started_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None
    state: str = "running"
    step: str | None = None
    steps: dict[str, RestoreStepOut] = field(default_factory=dict)
    result: RestoreResultOut | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        for key, label in STEPS:
            self.steps[key] = RestoreStepOut(key=key, label_de=label, state="pending")  # type: ignore[arg-type]

    def progress(self) -> float:
        finished = sum(1 for step in self.steps.values() if step.state in ("done", "skipped"))
        return round(finished / len(self.steps), 3)


@dataclass(slots=True)
class _Opened:
    dump: Path
    keys_dir: Path | None
    manifest: dict[str, Any] | None
    checksum_ok: bool
    notes: list[str]


@dataclass(slots=True)
class _Analysis:
    """Alles, was Vorschau und Ausführung aus Sicherung und jetzigem Stand ermitteln."""

    opened: _Opened
    info: dumpinfo.DumpInfo
    schema: SchemaCheckOut
    keys: KeyPlan
    access: AccessCheckOut
    comparison: ComparisonOut
    tournaments: list[TournamentPreviewOut]
    persons: int | None
    records: list[dict[str, Any]]
    problems: list[str]
    notes: list[str]


class RestoreManager:
    def __init__(self, app: FastAPI, backup: BackupService, maintenance: MaintenanceState) -> None:
        self.app = app
        self.backup = backup
        self.maintenance = maintenance
        self.pre_restore_dir = backup.snapshot_dir.parent / PRE_RESTORE_DIR
        self._job: _Job | None = None
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    # --- Quellen ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _usb_sources(self) -> list[Source]:
        if not self.backup.usb.present:
            return []
        try:
            return await self.backup._in_usb_thread(
                _scan,
                self.backup.usb_dir / usb.SNAPSHOT_DIR,
                "usb",
                limit_s=self.backup.usb_timeout_seconds,
                executor=self.backup._verify_executor,
            )
        except (TimeoutError, OSError) as exc:
            logger.warning("Sicherungen auf dem Stick nicht lesbar: %s", exc)
            return []

    def _journal_dirs(self) -> list[Path]:
        return [self.backup.journal.directory, self.backup.usb_dir / usb.JOURNAL_DIR]

    def _describe(self, source: Source, days: set[str]) -> RestoreSourceOut:
        stat = source.path.stat()
        day = source.created_at.strftime("%Y-%m-%d")
        return RestoreSourceOut(
            id=source.id,
            location=source.location,  # type: ignore[arg-type]
            file_name=source.path.name,
            created_at=source.created_at,
            size_bytes=stat.st_size,
            checksum_present=fsutil.checksum_path(source.path).is_file(),
            encrypted=source.encrypted,
            needs_passphrase=source.encrypted,
            contains_keys=source.contains_keys,
            journal_available=any(item >= day for item in days),
        )

    async def list_sources(self) -> RestoreSourcesOut:
        local = await asyncio.to_thread(_scan, self.backup.snapshot_dir, "local")
        before = await asyncio.to_thread(_scan, self.pre_restore_dir, "pre_restore")
        stick = await self._usb_sources()
        days = await asyncio.to_thread(_journal_days, self._journal_dirs())
        sources = sorted(
            [*stick, *local, *before], key=lambda item: (item.created_at, item.id), reverse=True
        )
        described = []
        for source in sources:
            with contextlib.suppress(OSError):
                described.append(await asyncio.to_thread(self._describe, source, days))
        return RestoreSourcesOut(
            usb_present=self.backup.usb.present,
            sources=described,
            restore_running=self.running,
        )

    def _resolve(self, source_id: str) -> Source:
        location, _, name = source_id.partition(":")
        created = _created_at(name)
        if (
            location not in _SUFFIXES
            or created is None
            or Path(name).suffix not in _SUFFIXES[location]
        ):
            raise NotFoundError("Diese Sicherung gibt es nicht.")
        directory = {
            "usb": self.backup.usb_dir / usb.SNAPSHOT_DIR,
            "local": self.backup.snapshot_dir,
            "pre_restore": self.pre_restore_dir,
        }[location]
        if location == "usb" and not self.backup.usb.present:
            raise ConflictError("Der Stick mit dieser Sicherung steckt nicht.")
        path = directory / name
        if not path.is_file():
            raise NotFoundError("Diese Sicherung gibt es nicht (mehr).")
        return Source(location, path, created)

    # --- Lesen und Vergleichen -------------------------------------------------------

    async def _open(self, source: Source, passphrase: str | None, work: Path) -> _Opened:
        if source.location != "usb":
            return await asyncio.to_thread(self._copy_dump, source.path, work)
        if source.encrypted and not passphrase:
            raise BackupError("Bitte das Sicherungspasswort angeben.")
        try:
            _size, file_ok, contents = await self.backup._in_usb_thread(
                _open_backup,
                source.path,
                passphrase if source.encrypted else None,
                work,
                limit_s=self.backup.usb_copy_timeout_seconds,
                executor=self.backup._verify_executor,
            )
        except FileNotFoundError:
            raise NotFoundError("Diese Sicherung liegt nicht mehr auf dem Stick.") from None
        except crypto.WrongPassphraseError:
            raise BackupError("Das Sicherungspasswort ist falsch.") from None
        except (crypto.BackupCryptoError, archive.ArchiveError) as exc:
            raise BackupError(f"Die Sicherung ist beschädigt: {exc}") from None
        except TimeoutError:
            raise BackupError("Der Sicherungs-Stick hat nicht rechtzeitig geantwortet.") from None
        except OSError as exc:
            raise BackupError(f"Die Sicherung ist nicht lesbar: {exc.strerror or exc}") from None
        if not contents.database_sha256_ok or contents.database_file is None:
            raise BackupError(
                "Die Sicherung ist beschädigt: Die Prüfsumme des Datenbank-Abzugs weicht ab."
            )
        notes = []
        if fsutil.checksum_path(source.path).is_file() and not file_ok:
            raise BackupError("Die Sicherung ist beschädigt: Die Prüfsumme der Datei weicht ab.")
        if not file_ok:
            notes.append(
                "Zur Datei liegt keine Prüfsumme (.sha256); geprüft wurde die Prüfsumme des "
                "Abzugs im Archiv."
            )
        return _Opened(
            dump=contents.database_file,
            keys_dir=contents.keys_dir,
            manifest=contents.manifest,
            checksum_ok=True,
            notes=notes,
        )

    @staticmethod
    def _copy_dump(path: Path, work: Path) -> _Opened:
        expected = fsutil.read_checksum(path)
        if expected is None:
            raise BackupError("Zu diesem Abzug fehlt die Prüfsumme (.sha256).")
        target = work / archive.DATABASE_NAME
        with path.open("rb") as source, target.open("wb") as out:
            writer = fsutil.HashingWriter(out)
            shutil.copyfileobj(source, writer)
        if writer.hexdigest() != expected:
            target.unlink(missing_ok=True)
            raise BackupError("Der Abzug ist beschädigt: Die Prüfsumme weicht ab.")
        return _Opened(
            dump=target,
            keys_dir=None,
            manifest=None,
            checksum_ok=True,
            notes=["Abzug vom Server ohne Schlüssel: Es gelten die Schlüssel des Servers."],
        )

    def _read_journals(self, passphrase: str | None) -> tuple[list[dict[str, Any]], int, list[str]]:
        """Ergebnis-Ereignisse aus der Mitschrift auf dem Server und (wenn lesbar) dem Stick."""
        entries: list[journal.JournalEntry] = []
        files = 0
        unreadable: list[str] = []
        for path in self.backup.journal.segment_paths():
            entries.extend(journal.read_entries(path))
            files += 1
        keys: dict[bytes, crypto.BackupKey] = {}
        if self.backup.key is not None:
            keys[self.backup.key.key_header] = self.backup.key
        stick = self.backup.usb_dir / usb.JOURNAL_DIR
        if self.backup.usb.present and stick.is_dir():
            for path in sorted(stick.glob(f"{journal.SEGMENT_PREFIX}*")):
                try:
                    entries.extend(self._read_usb_journal(path, passphrase, keys))
                    files += 1
                except crypto.BackupCryptoError, OSError:
                    unreadable.append(path.name)
        return journal_apply.result_records(entries), files, unreadable

    @staticmethod
    def _read_usb_journal(
        path: Path, passphrase: str | None, keys: dict[bytes, crypto.BackupKey]
    ) -> list[journal.JournalEntry]:
        if path.name.endswith(journal.SEGMENT_SUFFIX):
            return journal.read_entries(path)
        with path.open("rb") as file:
            header = crypto.parse_journal_header_line(file.readline())
            key = keys.get(header)
            if key is None:
                if passphrase is None:
                    raise crypto.WrongPassphraseError()
                key = crypto.unwrap_key(header, passphrase)
                keys[header] = key
            return journal.decrypt_lines(key, file)

    async def _live(self, actor: Actor) -> dict[str, Any]:
        from app.modules.auth.models import AuthSession
        from app.modules.ergebnisse.models import ResultEvent
        from app.modules.starts.models import Start
        from app.modules.teilnehmer.models import Person

        async with self.backup.session_factory() as session:
            events = {str(row.id) for row in await session.execute(select(ResultEvent.id))}
            starts = {str(row.id) for row in await session.execute(select(Start.id))}
            persons = await session.scalar(select(func.count()).select_from(Person)) or 0
            sessions: set[str] = set()
            pin_hash: str | None = None
            if actor.user_id is not None:
                from app.modules.auth.models import UserAccount

                statement = select(AuthSession.id).where(
                    AuthSession.user_id == actor.user_id, AuthSession.expires_at > _now()
                )
                if actor.device_id is not None:
                    statement = statement.where(AuthSession.device_id == actor.device_id)
                sessions = {str(value) for value in await session.scalars(statement)}
                pin_hash = await session.scalar(
                    select(UserAccount.pin_hash).where(UserAccount.id == actor.user_id)
                )
        return {
            "events": events,
            "starts": starts,
            "persons": persons,
            "sessions": sessions,
            "pin_hash": pin_hash,
        }

    def _enforced_now(self) -> bool:
        state = getattr(self.app.state, "auth_enforcement", None)
        if state is not None:
            return bool(getattr(state, "enforced", False))
        auth_settings = getattr(self.app.state, "auth_settings", None)
        if auth_settings is not None:
            return bool(getattr(auth_settings, "enforced", False))
        return bool(self.app.state.settings.auth_enforced)

    def _access(
        self, actor: Actor, info: dumpinfo.DumpInfo, live: dict[str, Any]
    ) -> AccessCheckOut:
        enforced_now = self._enforced_now()
        stored = next(
            (
                row.get("value")
                for row in info.rows("setting") or []
                if row.get("key") == AUTH_ENFORCEMENT_KEY
            ),
            None,
        )
        try:
            enforced_backup = bool(json.loads(stored).get("enforced")) if stored else False
        except ValueError, AttributeError:
            enforced_backup = False
        enforced_after = enforced_now or enforced_backup
        roles = {row["id"]: row for row in info.rows("role") or [] if row.get("id")}

        def is_admin(role_id: str | None) -> bool:
            role = roles.get(role_id or "")
            if role is None:
                return False
            if _is_true(role.get("is_system")):
                return True
            try:
                entries = json.loads(role.get("permissions") or "[]")
            except ValueError:
                return False
            return "*" in entries or "backup.restore" in entries

        users = {row["id"]: row for row in info.rows("user_account") or [] if row.get("id")}
        admins = sum(
            1
            for row in users.values()
            if _is_true(row.get("active")) and is_admin(row.get("role_id"))
        )
        if actor.user_id is None:
            risk = enforced_after and not enforced_now
            message = (
                "Nach der Wiederherstellung ist die Berechtigungsprüfung eingeschaltet (so stand "
                "es in der Sicherung). Anmelden geht dann nur mit einem Konto und einem Gerät "
                f"aus der Sicherung ({admins} Administrator(en) mit PIN). " + CONSOLE_HINT
                if risk
                else "Die Berechtigungsprüfung ist aus; der Zugang ändert sich nicht."
            )
            return AccessCheckOut(
                enforced_now=enforced_now,
                enforced_after=enforced_after,
                account_in_backup=None,
                account_is_admin_in_backup=None,
                device_in_backup=None,
                session_in_backup=None,
                pin_changed=None,
                admins_in_backup=admins if info.rows("user_account") is not None else None,
                lockout_risk=risk,
                message_de=message,
            )
        user = users.get(str(actor.user_id))
        account = user is not None and _is_true(user.get("active"))
        admin = account and is_admin(user.get("role_id") if user else None)
        devices = {row["id"]: row for row in info.rows("device") or [] if row.get("id")}
        device_row = devices.get(str(actor.device_id)) if actor.device_id else None
        device = device_row is not None and not _is_true(device_row.get("blocked"))
        now = _now()
        session_ok = any(
            row.get("id") in live["sessions"] and (_parse_time(row.get("expires_at")) or now) > now
            for row in info.rows("session") or []
        )
        pin_changed = (
            None
            if user is None or live["pin_hash"] is None
            else user.get("pin_hash") != live["pin_hash"]
        )
        risk = enforced_after and not (account and admin and device)
        parts: list[str] = []
        if not enforced_after:
            parts.append("Die Berechtigungsprüfung ist aus; der Zugang ändert sich nicht.")
        elif risk:
            missing = []
            if not account:
                missing.append("dein Konto")
            elif not admin:
                missing.append("deine Administrator-Rolle")
            if not device:
                missing.append("dieses Gerät")
            parts.append(
                "In der Sicherung fehlt " + " und ".join(missing) + ". Nach der Wiederherstellung "
                "kommst du an diesem Gerät nicht mehr in die Verwaltung. " + CONSOLE_HINT
            )
        elif session_ok:
            parts.append("Konto und Gerät sind in der Sicherung; du bleibst angemeldet.")
        else:
            parts.append(
                "Konto und Gerät sind in der Sicherung. Danach bitte neu mit der PIN anmelden."
            )
        if enforced_after and pin_changed:
            parts.append("Achtung: In der Sicherung gilt deine frühere PIN.")
        return AccessCheckOut(
            enforced_now=enforced_now,
            enforced_after=enforced_after,
            account_in_backup=account,
            account_is_admin_in_backup=admin,
            device_in_backup=device,
            session_in_backup=session_ok,
            pin_changed=pin_changed,
            admins_in_backup=admins,
            lockout_risk=risk,
            message_de=" ".join(parts),
        )

    @staticmethod
    def _tournaments(info: dumpinfo.DumpInfo) -> list[TournamentPreviewOut]:
        competitions = {
            row["id"]: row.get("tournament_id") for row in info.rows("competition") or []
        }
        start_tournament = {
            row["id"]: competitions.get(row.get("competition_id") or "")
            for row in info.rows("start") or []
        }
        counts: dict[str, dict[str, int]] = {}

        def bump(tournament: str | None, key: str) -> None:
            if tournament is not None:
                bucket = counts.setdefault(tournament, {"starts": 0, "final": 0, "events": 0})
                bucket[key] += 1

        for tournament in start_tournament.values():
            bump(tournament, "starts")
        for row in info.rows("result_current") or []:
            if _is_true(row.get("is_final")):
                bump(start_tournament.get(row.get("start_id") or ""), "final")
        for row in info.rows("result_event") or []:
            bump(start_tournament.get(row.get("start_id") or ""), "events")
        result = []
        for row in info.rows("tournament") or []:
            bucket = counts.get(row["id"], {"starts": 0, "final": 0, "events": 0})
            result.append(
                TournamentPreviewOut(
                    id=uuid.UUID(row["id"]),
                    name=row.get("name") or "",
                    status=row.get("status") or "",
                    date_from=row.get("date_from"),
                    starts=bucket["starts"],
                    final_results=bucket["final"],
                    result_events=bucket["events"],
                )
            )
        return sorted(result, key=lambda item: (item.date_from or "", item.name), reverse=True)

    @staticmethod
    def _comparison(
        info: dumpinfo.DumpInfo,
        live: dict[str, Any],
        records: list[dict[str, Any]],
        journal_files: int,
        unreadable: list[str],
    ) -> ComparisonOut:
        backup_events = info.rows("result_event") or []
        by_start: dict[str, dict[str, int]] = {}
        for row in backup_events:
            by_start.setdefault(row["start_id"] or "", {})[row["id"] or ""] = int(row["seq"] or 0)
        starts = {
            row["id"]: journal_apply.BackupStart(
                entry_id=row.get("entry_id") or "",
                competition_id=row.get("competition_id") or "",
                events=by_start.get(row["id"] or "", {}),
            )
            for row in info.rows("start") or []
            if row.get("id")
        }
        plan = journal_apply.plan_records(records, starts)
        backup_ids = {row["id"] for row in backup_events if row.get("id")}
        live_ids: set[str] = live["events"]
        since = live_ids - backup_ids
        applied = since & plan.applied
        lost = since - applied
        lost_missing = len(lost & plan.missing_start_events)
        lost_conflict = len((lost & plan.conflict_events) - plan.missing_start_events)
        lost_not_in_journal = len(lost) - lost_missing - lost_conflict
        starts_since = len(live["starts"] - set(starts))
        summary = (
            f"Seit dieser Sicherung sind {len(since)} Ergebnis-Ereignisse hinzugekommen; davon "
            f"stehen {len(applied)} in der Mitschrift und werden nachgetragen, {len(lost)} gehen "
            "verloren."
        )
        reasons = []
        if lost_missing:
            reasons.append(
                f"{lost_missing} gehören zu Starts, die erst nach der Sicherung gebucht wurden"
            )
        if lost_not_in_journal:
            reasons.append(f"{lost_not_in_journal} stehen nicht in der Mitschrift")
        if lost_conflict:
            reasons.append(f"{lost_conflict} passen nicht zur Sicherung")
        if reasons:
            summary += " Davon " + ", ".join(reasons) + "."
        if starts_since:
            summary += (
                f" {starts_since} Start(s) wurden nach der Sicherung gebucht und fehlen danach."
            )
        extra = len(plan.applied - since - backup_ids)
        if extra:
            summary += (
                f" Zusätzlich trägt die Mitschrift {extra} Ereignisse nach, die heute fehlen."
            )
        return ComparisonOut(
            events_now=len(live_ids),
            events_in_backup=len(backup_ids),
            events_since_backup=len(since),
            events_from_journal=len(applied),
            events_lost=len(lost),
            lost_start_missing=lost_missing,
            lost_not_in_journal=lost_not_in_journal,
            lost_conflict=lost_conflict,
            events_only_in_backup=len(backup_ids - live_ids),
            journal_applicable=len(plan.applied),
            starts_now=len(live["starts"]),
            starts_in_backup=len(starts),
            starts_since_backup=starts_since,
            journal_files=journal_files,
            journal_unreadable=unreadable,
            summary_de=summary,
        )

    async def _privileges(self) -> list[str]:
        """Darf der Datenbank-Benutzer der App Datenbanken anlegen und die laufende umbenennen?"""
        target = pgtools.PgTarget.from_url(self.backup.settings.database_url)
        try:
            admin = await _connect(target, "postgres")
        except (OSError, asyncpg.PostgresError) as exc:
            return [f"Keine Verbindung zur Verwaltungs-Datenbank „postgres“: {exc}"]
        try:
            row = await admin.fetchrow(
                "SELECT r.rolsuper, r.rolcreatedb, pg_get_userbyid(d.datdba) = current_user "
                "AS owner FROM pg_roles r, pg_database d "
                "WHERE r.rolname = current_user AND d.datname = $1",
                target.database,
            )
        finally:
            await admin.close()
        problems = []
        if row is None:
            return [f"Die Datenbank „{target.database}“ wurde nicht gefunden."]
        if not (row["rolsuper"] or row["rolcreatedb"]):
            problems.append(
                f"Der Datenbank-Benutzer „{target.user}“ darf keine Datenbanken anlegen "
                "(CREATEDB fehlt). Bitte über die Konsole wiederherstellen oder das Recht "
                "vergeben."
            )
        if not (row["rolsuper"] or row["owner"]):
            problems.append(
                f"Der Datenbank-Benutzer „{target.user}“ ist nicht Eigentümer der Datenbank "
                f"„{target.database}“ und kann sie nicht umbenennen."
            )
        return problems

    async def _analyse(
        self, source: Source, passphrase: str | None, actor: Actor, work: Path
    ) -> _Analysis:
        opened = await self._open(source, passphrase, work)
        try:
            info = await dumpinfo.read_dump(opened.dump)
        except pgtools.PgToolError as exc:
            raise BackupError(f"Der Datenbank-Abzug ist nicht lesbar: {exc}") from None
        live = await self._live(actor)
        records, files, unreadable = await asyncio.to_thread(self._read_journals, passphrase)
        schema = schema_check(
            info.schema_revisions, await live_revisions(self.backup.session_factory)
        )
        keys = await asyncio.to_thread(
            plan_keys, opened.keys_dir, self.backup.keys_dir, live["persons"]
        )
        problems: list[str] = []
        if schema.state == "newer":
            problems.append(schema.message_de)
        if keys.conflicts:
            problems.append(keys.message())
        problems.extend(await self._privileges())
        persons = info.rows("person")
        manifest = opened.manifest or {}
        notes = list(opened.notes)
        if manifest.get("app_version") and manifest["app_version"] != __version__:
            notes.append(
                f"Die Sicherung stammt von App-Version {manifest['app_version']}, laufend ist "
                f"{__version__}."
            )
        return _Analysis(
            opened=opened,
            info=info,
            schema=schema,
            keys=keys,
            access=self._access(actor, info, live),
            comparison=self._comparison(info, live, records, files, unreadable),
            tournaments=self._tournaments(info),
            persons=None if persons is None else len(persons),
            records=records,
            problems=problems,
            notes=notes,
        )

    def _work_dir(self) -> Path:
        self.backup.work_dir.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="restore-", dir=self.backup.work_dir))

    async def preview(self, body: RestorePreviewIn, actor: Actor) -> RestorePreviewOut:
        source = self._resolve(body.source_id)
        described = await asyncio.to_thread(
            self._describe, source, await asyncio.to_thread(_journal_days, self._journal_dirs())
        )
        work = await asyncio.to_thread(self._work_dir)
        try:
            analysis = await self._analyse(source, body.passphrase, actor, work)
        finally:
            await asyncio.to_thread(shutil.rmtree, work, True)
        manifest = analysis.opened.manifest or {}
        problems = list(analysis.problems)
        if self.running:
            problems.append("Es läuft bereits eine Wiederherstellung.")
        return RestorePreviewOut(
            source=described,
            confirm=described.id,
            checksum_ok=analysis.opened.checksum_ok,
            created_at=_parse_time(manifest.get("created_at")) or source.created_at,
            app_version=manifest.get("app_version"),
            app_version_current=__version__,
            schema_check=analysis.schema,
            tournaments=analysis.tournaments,
            persons=analysis.persons,
            comparison=analysis.comparison,
            keys=analysis.keys.out(),
            access=analysis.access,
            restorable=not problems,
            problems=problems,
            notes=analysis.notes,
        )

    # --- Ausführen -----------------------------------------------------------------

    def status(self) -> RestoreStatusOut:
        job = self._job
        maintenance = self.maintenance.active
        if job is None:
            return RestoreStatusOut(
                state="idle",
                step=None,
                progress=0.0,
                steps=[
                    RestoreStepOut(key=key, label_de=label, state="pending")  # type: ignore[arg-type]
                    for key, label in STEPS
                ],
                source=None,
                started_at=None,
                finished_at=None,
                result=None,
                error_de=None,
                maintenance=maintenance,
            )
        return RestoreStatusOut(
            state=job.state,  # type: ignore[arg-type]
            step=job.step,  # type: ignore[arg-type]
            progress=1.0 if job.state == "succeeded" else job.progress(),
            steps=list(job.steps.values()),
            source=job.source,
            started_at=job.started_at,
            finished_at=job.finished_at,
            result=job.result,
            error_de=job.error,
            maintenance=maintenance,
        )

    async def execute(self, body: RestoreExecuteIn, actor: Actor) -> RestoreStatusOut:
        if body.confirm != body.source_id:
            raise BackupError(
                "Bitte die Wiederherstellung ausdrücklich bestätigen: `confirm` muss die Kennung "
                "der Sicherung enthalten."
            )
        async with self._lock:
            if self.running:
                raise ConflictError("Es läuft bereits eine Wiederherstellung.")
            source = self._resolve(body.source_id)
            if source.encrypted and not body.passphrase:
                raise BackupError("Bitte das Sicherungspasswort angeben.")
            days = await asyncio.to_thread(_journal_days, self._journal_dirs())
            described = await asyncio.to_thread(self._describe, source, days)
            job = _Job(
                source=described,
                actor=actor,
                passphrase=body.passphrase,
                apply_journal=body.apply_journal,
                accept_lockout=body.accept_lockout,
            )
            self._job = job
            self._task = asyncio.create_task(self._run(job, source), name="backup-restore")
        self._publish(job)
        return self.status()

    async def stop(self) -> None:
        """Beim Beenden: vor dem Tausch abbrechen, einen laufenden Tausch zu Ende bringen."""
        task = self._task
        if task is None or task.done():
            return
        job = self._job
        if job is not None and job.step in ("swap", "finish"):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(task), 120)
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    def _publish(self, job: _Job) -> None:
        # Für alle Geräte: nur Zustand und Schritt, keine Dateinamen oder Fehlertexte.
        self.app.state.events.publish(
            EVENT_RESTORE, {"state": job.state, "step": job.step, "progress": job.progress()}
        )

    def _set(self, job: _Job, key: str, state: str, detail: str | None = None) -> None:
        job.steps[key] = job.steps[key].model_copy(update={"state": state, "detail_de": detail})
        if state == "running":
            job.step = key
        self._publish(job)

    @contextlib.asynccontextmanager
    async def _step(self, job: _Job, key: str) -> Any:
        self._set(job, key, "running")
        try:
            yield
        except BaseException as exc:
            detail = str(exc) if isinstance(exc, (RestoreFailed, BackupError)) else None
            self._set(job, key, "failed", detail)
            raise
        if job.steps[key].state == "running":
            self._set(job, key, "done", job.steps[key].detail_de)

    async def _run(self, job: _Job, source: Source) -> None:
        target = pgtools.PgTarget.from_url(self.backup.settings.database_url)
        work = await asyncio.to_thread(self._work_dir)
        started = _now()
        stamp = _stamp(started)
        staging = _derived_name(target.database, f"_restore_{stamp}")
        previous = _derived_name(target.database, f"_pre_restore_{stamp}")
        staging_created = False
        try:
            async with self._step(job, "check"):
                try:
                    analysis = await self._analyse(source, job.passphrase, job.actor, work)
                except BackupError as exc:
                    raise RestoreFailed(str(exc)) from None
                if analysis.problems:
                    raise RestoreFailed(" ".join(analysis.problems))
                if analysis.access.lockout_risk and not job.accept_lockout:
                    raise RestoreFailed(
                        analysis.access.message_de
                        + " Zum Fortfahren bitte ausdrücklich bestätigen (`accept_lockout`)."
                    )

            async with self._step(job, "maintenance"):
                self.maintenance.begin()
                if not await self.maintenance.drained(DRAIN_WRITES_S):
                    raise RestoreFailed(
                        "Begonnene Eingaben sind nicht rechtzeitig fertig geworden; bitte später "
                        "erneut versuchen."
                    )

            pre_runs: list[RunOut] = []
            pre_name: str | None = None
            async with self._step(job, "pre_backup"):
                pre_runs = await self.backup.run_snapshot()
                local = pre_runs[0]
                if not local.ok or local.file_name is None:
                    raise RestoreFailed(
                        f"Die Sicherung des jetzigen Stands ist fehlgeschlagen: {local.error}"
                    )
                pre_name = await asyncio.to_thread(self._keep_pre_restore, local.file_name)
                if len(pre_runs) > 1 and not pre_runs[1].ok:
                    self._set(
                        job,
                        "pre_backup",
                        "running",
                        f"Auf dem Server gesichert; Kopie auf den Stick fehlgeschlagen: "
                        f"{pre_runs[1].error}",
                    )

            staging_url = (
                make_url(self.backup.settings.database_url)
                .set(database=staging)
                .render_as_string(hide_password=False)
            )
            async with self._step(job, "load"):
                await self._create_database(target, staging)
                staging_created = True
                try:
                    await pgtools.restore(
                        target.with_database(staging), analysis.opened.dump, RESTORE_TIMEOUT_S
                    )
                except pgtools.PgToolError as exc:
                    raise RestoreFailed(f"Einspielen fehlgeschlagen: {exc}") from None

            upgraded = False
            async with self._step(job, "upgrade"):
                if analysis.schema.state == "older":
                    for revision in analysis.schema.current:
                        await _alembic_upgrade(staging_url, revision)
                    upgraded = True
                else:
                    self._set(job, "upgrade", "skipped", "Die Sicherung passt zur App.")

            report: journal_apply.ApplyReport | None = None
            async with self._step(job, "journal"):
                if not job.apply_journal:
                    self._set(job, "journal", "skipped", "Nachtragen abgewählt.")
                elif not analysis.records:
                    self._set(job, "journal", "skipped", "Keine Ereignisse in der Mitschrift.")
                else:
                    report = await self._apply_journal(staging_url, analysis.records)
                    self._set(job, "journal", "running", report.summary()[0])

            async with self._step(job, "verify"):
                await self._verify_and_carry_over(staging_url, analysis)

            moved: list[tuple[Path, Path]] = []
            restart_notes: list[str] = []
            async with self._step(job, "swap"), self.backup._snapshot_lock:
                self.maintenance.set_exclusive(True)
                await self.maintenance.drained(DRAIN_READS_S, reads=True)
                await self._stop_modules()
                try:
                    if analysis.opened.keys_dir is not None:
                        moved = await asyncio.to_thread(
                            apply_keys,
                            analysis.keys,
                            analysis.opened.keys_dir,
                            self.backup.keys_dir,
                            stamp,
                        )
                    try:
                        await self._swap(target, staging, previous)
                    except BaseException:
                        await asyncio.to_thread(
                            undo_keys, analysis.keys, self.backup.keys_dir, moved
                        )
                        raise
                    staging_created = False
                finally:
                    await self.app.state.engine.dispose()
                    restart_notes = await self._start_modules()
                    self.maintenance.set_exclusive(False)

            async with self._step(job, "finish"):
                notes = [*analysis.notes, *restart_notes]
                await self.backup.reload_from_database()
                await self._record_runs(pre_runs)
                await self._audit(job, analysis, previous, pre_name, report, upgraded)
                after = await self.backup.run_snapshot()
                after_ok = bool(after) and after[0].ok
                if not after_ok:
                    notes.append(
                        "Die Sicherung des wiederhergestellten Stands ist fehlgeschlagen; bitte "
                        "unter System → Sicherung „Jetzt sichern“."
                    )
                job.result = RestoreResultOut(
                    database=target.database,
                    previous_database=previous,
                    pre_restore_backup=pre_name,
                    schema_upgraded=upgraded,
                    journal=_journal_out(report),
                    keys_installed=list(analysis.keys.install),
                    keys_set_aside=[aside.name for _target, aside in moved],
                    after_backup_ok=after_ok,
                    notes=notes,
                )
            job.state = "succeeded"
            logger.warning(
                "Sicherung %s wiederhergestellt; vorherige Datenbank: %s.", source.id, previous
            )
        except asyncio.CancelledError:
            job.state = "failed"
            job.error = "Die Wiederherstellung wurde abgebrochen (Server beendet)."
            raise
        except RestoreFailed as exc:
            job.state = "failed"
            job.error = str(exc)
            logger.warning("Wiederherstellung abgebrochen: %s", exc)
        except Exception as exc:
            job.state = "failed"
            job.error = f"Unerwarteter Fehler: {type(exc).__name__}: {exc}"
            logger.exception("Wiederherstellung fehlgeschlagen.")
        finally:
            job.passphrase = None
            job.finished_at = _now()
            if staging_created:
                with contextlib.suppress(Exception):
                    await self._drop_database(target, staging)
            await asyncio.to_thread(shutil.rmtree, work, True)
            self.maintenance.end()
            self._publish(job)

    # --- Bausteine der Ausführung ------------------------------------------------------

    def _keep_pre_restore(self, file_name: str) -> str:
        """Kopiert den Abzug „vor Wiederherstellung“ aus der Rotation heraus."""
        source = self.backup.snapshot_dir / file_name
        self.pre_restore_dir.mkdir(parents=True, exist_ok=True)
        target = self.pre_restore_dir / file_name
        shutil.copyfile(source, target)
        with target.open("rb+") as file:
            os.fsync(file.fileno())
        os.chmod(target, 0o600)
        digest = fsutil.read_checksum(source) or fsutil.sha256_file(target)
        fsutil.write_checksum(target, digest)
        return f"{PRE_RESTORE_DIR}/{file_name}"

    async def _create_database(self, target: pgtools.PgTarget, name: str) -> None:
        admin = await _connect(target, "postgres")
        try:
            await admin.execute(f"CREATE DATABASE {_quote(name)}")
        except asyncpg.InsufficientPrivilegeError:
            raise RestoreFailed(
                f"Der Datenbank-Benutzer „{target.user}“ darf keine Datenbank anlegen (CREATEDB)."
            ) from None
        finally:
            await admin.close()

    async def _drop_database(self, target: pgtools.PgTarget, name: str) -> None:
        admin = await _connect(target, "postgres")
        try:
            await admin.execute(f"DROP DATABASE IF EXISTS {_quote(name)} WITH (FORCE)")
        finally:
            await admin.close()

    async def _apply_journal(
        self, url: str, records: list[dict[str, Any]]
    ) -> journal_apply.ApplyReport:
        engine = create_engine(url)
        try:
            return await journal_apply.apply_records(create_session_factory(engine), records)
        finally:
            await engine.dispose()

    async def _verify_and_carry_over(self, url: str, analysis: _Analysis) -> None:
        engine = create_engine(url)
        try:
            async with engine.connect() as connection:
                versions = sorted(
                    await connection.scalars(text("SELECT version_num FROM alembic_version"))
                )
                # Gleicher Stand wie die laufende Datenbank: Der Server läuft danach unverändert.
                if versions != analysis.schema.current:
                    raise RestoreFailed(
                        "Die neue Datenbank hat nicht den Stand der laufenden ("
                        + ", ".join(versions)
                        + ")."
                    )
                roles = await connection.scalar(text("SELECT count(*) FROM role"))
                system = await connection.scalar(text("SELECT count(*) FROM role WHERE is_system"))
                if roles and not system:
                    raise RestoreFailed("In der Sicherung fehlt die Systemrolle Administrator.")
                samples = list(
                    await connection.scalars(
                        text("SELECT name_enc FROM person ORDER BY created_at LIMIT 5")
                    )
                )
            if samples:
                cipher = self._cipher_after(analysis)
                try:
                    for value in samples:
                        cipher.decrypt(bytes(value))
                except field_crypto.CryptoError:
                    raise RestoreFailed(
                        "Die Namen der Sicherung lassen sich mit den Schlüsseln nicht lesen."
                    ) from None
            await self._carry_over(engine)
        finally:
            await engine.dispose()

    def _cipher_after(self, analysis: _Analysis) -> field_crypto.FieldCipher:
        """Der Namensschlüssel, der nach dem Tausch gilt."""
        source = analysis.opened.keys_dir
        if source is not None and analysis.keys.field_keys in ("install", "replace_unused"):
            return field_crypto.FieldCipher(field_crypto.load_keyring(source, create=False))
        return field_crypto.FieldCipher(
            field_crypto.load_keyring(self.backup.keys_dir, create=False)
        )

    async def _carry_over(self, engine: Any) -> None:
        """Übernimmt Server-Einstellungen aus dem jetzigen Stand in die neue Datenbank.

        - `backup`: Einrichtung der Sicherung (Ziel, Takt, Verschlüsselung) gehört zum Server,
          nicht zum Datenstand; ebenso bleibt das heutige Sicherungspasswort.
        - `auth_enforcement`: Ist die Berechtigungsprüfung jetzt eingeschaltet, bleibt sie es.
        """
        async with self.backup.session_factory() as live:
            rows = {
                row.key: row.value
                for row in await live.execute(
                    select(Setting.key, Setting.value).where(
                        Setting.key.in_([SETTINGS_KEY, AUTH_ENFORCEMENT_KEY])
                    )
                )
            }
        carry = {}
        if SETTINGS_KEY in rows:
            carry[SETTINGS_KEY] = rows[SETTINGS_KEY]
        enforcement = rows.get(AUTH_ENFORCEMENT_KEY)
        if isinstance(enforcement, dict) and enforcement.get("enforced"):
            carry[AUTH_ENFORCEMENT_KEY] = enforcement
        if not carry:
            return
        async with create_session_factory(engine)() as session, session.begin():
            for key, value in carry.items():
                statement = insert(Setting).values(key=key, value=value)
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[Setting.key],
                        set_={"value": value, "updated_at": func.now()},
                    )
                )

    async def _swap(self, target: pgtools.PgTarget, staging: str, previous: str) -> None:
        live = target.database
        admin = await _connect(target, "postgres")
        try:
            await admin.execute(f"ALTER DATABASE {_quote(live)} ALLOW_CONNECTIONS false")
            try:
                await self.app.state.engine.dispose()
                await _rename_when_free(admin, live, previous)
            except BaseException:
                await admin.execute(f"ALTER DATABASE {_quote(live)} ALLOW_CONNECTIONS true")
                raise
            try:
                await _rename_when_free(admin, staging, live)
            except BaseException:
                await admin.execute(f"ALTER DATABASE {_quote(previous)} RENAME TO {_quote(live)}")
                await admin.execute(f"ALTER DATABASE {_quote(live)} ALLOW_CONNECTIONS true")
                raise
            await admin.execute(f"ALTER DATABASE {_quote(previous)} ALLOW_CONNECTIONS true")
        finally:
            await admin.close()

    def _other_modules(self) -> list[Any]:
        from app.modules import MODULES

        return [module for module in MODULES if module.name != "backup"]

    async def _stop_modules(self) -> None:
        for module in reversed(self._other_modules()):
            if module.on_shutdown is not None:
                try:
                    await module.on_shutdown(self.app)
                except Exception:
                    logger.exception("Modul %s ließ sich nicht anhalten.", module.name)

    async def _start_modules(self) -> list[str]:
        """Startet die übrigen Module neu, wie nach einem Neustart des Servers."""
        notes = []
        for module in self._other_modules():
            if module.on_startup is not None:
                try:
                    await module.on_startup(self.app)
                except Exception:
                    logger.exception("Modul %s ließ sich nicht neu starten.", module.name)
                    notes.append(
                        f"Das Modul „{module.title}“ ließ sich nicht neu starten; bitte den Server "
                        "neu starten."
                    )
        return notes

    async def _record_runs(self, runs: list[RunOut]) -> None:
        """Die Läufe „vor Wiederherstellung“ stehen sonst nur in der alten Datenbank."""
        if not runs:
            return
        try:
            async with self.backup.session_factory() as session, session.begin():
                for run in runs:
                    session.add(BackupRun(**run.model_dump()))
        except Exception:
            logger.exception("Sicherungsläufe vor der Wiederherstellung nicht übernommen.")

    async def _audit(
        self,
        job: _Job,
        analysis: _Analysis,
        previous: str,
        pre_name: str | None,
        report: journal_apply.ApplyReport | None,
        upgraded: bool,
    ) -> None:
        from app.modules.auth.audit import record_audit

        manifest = analysis.opened.manifest or {}
        details = {
            "source": job.source.id,
            "backup_created_at": manifest.get("created_at") or job.source.created_at.isoformat(),
            "previous_database": previous,
            "pre_restore_backup": pre_name,
            "schema_upgraded": upgraded,
            "keys_installed": list(analysis.keys.install),
            "journal": None
            if report is None
            else {
                "applied": report.applied,
                "present": report.present,
                "missing_events": report.missing_events,
                "conflicts": len(report.conflicts),
            },
            "via": "in der App",
        }
        async with self.backup.session_factory() as session, session.begin():
            record_audit(session, job.actor, "backup.restored", "backup", None, details)


def _journal_out(report: journal_apply.ApplyReport | None) -> JournalReportOut | None:
    if report is None:
        return None
    return JournalReportOut(
        applied=report.applied,
        present=report.present,
        missing_events=report.missing_events,
        conflicts=len(report.conflicts),
        status_changes=report.status_changes,
        recomputed_competitions=report.recomputed_competitions,
        lines=report.summary(),
    )


async def _connect(target: pgtools.PgTarget, database: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=target.host,
        port=target.port,
        user=target.user,
        password=target.password,
        database=database,
    )


async def _rename_when_free(admin: asyncpg.Connection, old: str, new: str) -> None:
    """Schließt fremde Verbindungen und benennt um; wiederholt, solange jemand verbunden ist."""
    for _attempt in range(RENAME_ATTEMPTS):
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            old,
        )
        try:
            await admin.execute(f"ALTER DATABASE {_quote(old)} RENAME TO {_quote(new)}")
            return
        except asyncpg.ObjectInUseError:
            await asyncio.sleep(0.25)
    raise RestoreFailed(
        f"Die Datenbank „{old}“ ist noch in Benutzung und ließ sich nicht tauschen."
    )


async def _alembic_upgrade(url: str, revision: str) -> None:
    """`alembic upgrade <revision>` auf der neuen Datenbank (Ziel: Stand der laufenden)."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        revision,
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(process.communicate(), MIGRATION_TIMEOUT_S)
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await asyncio.shield(process.wait())
        raise
    if process.returncode != 0:
        message = stderr.decode("utf-8", "replace").strip().splitlines()
        logger.warning("alembic upgrade auf der neuen Datenbank: %s", "\n".join(message[-20:]))
        raise RestoreFailed(
            "Die neue Datenbank ließ sich nicht auf den Stand der App bringen: "
            + (message[-1] if message else "ohne Meldung")
        )
