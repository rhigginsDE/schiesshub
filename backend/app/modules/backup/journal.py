"""Laufende Mitschrift: jede Zeile sofort lokal (NDJSON, fsync), später auf den Stick gespiegelt.

Lokale Zeile (ein JSON-Objekt je Zeile)::

    {"at": "...", "record": {...}, "seq": 17, "sha256": "<über at, record, seq>"}

`seq` zählt über alle Segmente hinweg. Je Kalendertag (UTC) gibt es ein Segment
`journal-JJJJ-MM-TT.ndjson`. Zeilen mit falscher Prüfsumme oder abgerissene Zeilen werden beim
Lesen übersprungen; nach einem Absturz beginnt die nächste Zeile in jedem Fall auf einer neuen
Zeile. Auf dem Stick liegt je Segment und Sicherungsschlüssel eine Datei
`journal-JJJJ-MM-TT.<schlüssel-id>.shbj` (Format siehe `crypto`), ohne Verschlüsselung eine Kopie
der lokalen Datei.
"""

import hashlib
import json
import os
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.modules.backup import crypto, fsutil

SEGMENT_PREFIX = "journal-"
SEGMENT_SUFFIX = ".ndjson"
USB_ENCRYPTED_SUFFIX = ".shbj"


@dataclass(frozen=True, slots=True)
class JournalEntry:
    seq: int
    line: bytes  # vollständige Zeile inklusive Zeilenende


def _digest(at: str, record: dict[str, Any], seq: int) -> str:
    canonical = json.dumps(
        {"at": at, "record": record, "seq": seq},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_line(line: bytes) -> JournalEntry | None:
    """Prüft eine Zeile; `None` bei abgerissenen oder veränderten Zeilen."""
    if not line.endswith(b"\n"):
        return None
    try:
        data = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("seq"), int):
        return None
    record, at = data.get("record"), data.get("at")
    if not isinstance(record, dict) or not isinstance(at, str):
        return None
    if data.get("sha256") != _digest(at, record, data["seq"]):
        return None
    return JournalEntry(seq=data["seq"], line=line)


def read_entries(path: Path) -> list[JournalEntry]:
    with path.open("rb") as file:
        return [entry for line in file if (entry := parse_line(line)) is not None]


def _terminate_torn_tail(path: Path) -> None:
    """Endet die Datei nicht mit einem Zeilenumbruch, wird einer angehängt."""
    with path.open("rb+") as file:
        file.seek(0, os.SEEK_END)
        if file.tell() == 0:
            return
        file.seek(-1, os.SEEK_END)
        if file.read(1) != b"\n":
            file.write(b"\n")
            file.flush()
            os.fsync(file.fileno())


class Journal:
    """Lokale Mitschrift. Threadsicher; `append` kehrt erst nach fsync zurück."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._lock = threading.Lock()
        self._last_seq = 0
        # Segmentname -> höchste lokale seq darin.
        self._segment_last_seq: dict[str, int] = {}
        self.appended_total = 0

    def open(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._lock:
            for path in self.segment_paths():
                _terminate_torn_tail(path)
                entries = read_entries(path)
                if entries:
                    last = max(entry.seq for entry in entries)
                    self._segment_last_seq[path.name] = last
                    self._last_seq = max(self._last_seq, last)

    def segment_paths(self) -> list[Path]:
        return sorted(self.directory.glob(f"{SEGMENT_PREFIX}*{SEGMENT_SUFFIX}"))

    def segment_last_seq(self) -> dict[str, int]:
        with self._lock:
            return dict(self._segment_last_seq)

    def count_after(self, mirrored: dict[str, int]) -> int:
        """Anzahl der lokalen Zeilen, die laut `mirrored` (Segment -> seq) noch fehlen."""
        total = 0
        local_last = self.segment_last_seq()
        for path in self.segment_paths():
            known = mirrored.get(path.name, 0)
            if local_last.get(path.name, 0) > known:
                total += sum(1 for entry in read_entries(path) if entry.seq > known)
        return total

    def append(self, record: dict[str, Any], now: datetime | None = None) -> int:
        if not isinstance(record, dict):
            raise TypeError("Ein Eintrag der Mitschrift muss ein dict sein.")
        now = now or datetime.now(UTC)
        at = now.isoformat()
        with self._lock:
            seq = self._last_seq + 1
            line = (
                json.dumps(
                    {"at": at, "record": record, "seq": seq, "sha256": _digest(at, record, seq)},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            name = f"{SEGMENT_PREFIX}{now.strftime('%Y-%m-%d')}{SEGMENT_SUFFIX}"
            path = self.directory / name
            is_new = not path.exists()
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, line)
                os.fsync(fd)
            finally:
                os.close(fd)
            if is_new:
                fsutil.fsync_dir(self.directory)
            self._last_seq = seq
            self._segment_last_seq[name] = seq
            self.appended_total += 1
            return seq


# --- Spiegel auf dem Stick ----------------------------------------------------------


def usb_file_name(segment: str, key: crypto.BackupKey | None) -> str:
    if key is None:
        return segment
    stem = segment.removesuffix(SEGMENT_SUFFIX)
    return f"{stem}.{key.key_id}{USB_ENCRYPTED_SUFFIX}"


def read_usb_file(path: Path, key: crypto.BackupKey | None) -> list[JournalEntry]:
    """Liest eine Spiegeldatei. Mit `key` verschlüsselt, sonst Klartext wie lokal."""
    if not path.exists():
        return []
    if key is None:
        return read_entries(path)
    with path.open("rb") as file:
        header = file.readline()
        if not header:
            return []
        if crypto.parse_journal_header_line(header) != key.key_header:
            raise crypto.CorruptBackupError(
                "Die Mitschrift auf dem Stick gehört zu einem anderen Sicherungsschlüssel."
            )
        return decrypt_lines(key, file)


def decrypt_lines(key: crypto.BackupKey, lines: Iterable[bytes]) -> list[JournalEntry]:
    entries = []
    for line in lines:
        if not line.endswith(b"\n"):
            continue
        plaintext = crypto.decrypt_line(key, line)
        if plaintext is not None and (entry := parse_line(plaintext)) is not None:
            entries.append(entry)
    return entries


def append_usb_file(path: Path, entries: list[JournalEntry], key: crypto.BackupKey | None) -> None:
    """Hängt Zeilen an die Spiegeldatei an und fsynct sie."""
    is_new = not path.exists() or path.stat().st_size == 0
    if not is_new:
        _terminate_torn_tail(path)
    with path.open("ab") as file:
        if is_new and key is not None:
            file.write(crypto.journal_header_line(key))
        for entry in entries:
            file.write(entry.line if key is None else crypto.encrypt_line(key, entry.line))
        file.flush()
        os.fsync(file.fileno())
    if is_new:
        fsutil.fsync_dir(path.parent)


def read_journal_file(path: Path, passphrase: str | None) -> list[JournalEntry]:
    """Für die Wiederherstellung: liest lokale, Klartext- oder verschlüsselte Mitschriften."""
    with path.open("rb") as file:
        first = file.readline()
        if not first.startswith(crypto.JOURNAL_PREFIX):
            file.seek(0)
            return [entry for line in file if (entry := parse_line(line)) is not None]
        if passphrase is None:
            raise crypto.WrongPassphraseError()
        key = crypto.unwrap_key(crypto.parse_journal_header_line(first), passphrase)
        return decrypt_lines(key, file)
