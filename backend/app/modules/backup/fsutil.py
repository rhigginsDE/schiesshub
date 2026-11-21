"""Sicheres Schreiben: temporäre Datei, fsync, atomar umbenennen, Verzeichnis fsyncen.

Eine halbfertige Datei trägt immer die Endung `.tmp` und ersetzt nie eine gültige.
"""

import contextlib
import hashlib
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO

TMP_SUFFIX = ".tmp"
CHECKSUM_SUFFIX = ".sha256"
_READ_SIZE = 1024 * 1024


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def drop_cache(file: BinaryIO) -> None:
    """Verwirft die Seiten der Datei im Cache, damit Zurücklesen den Datenträger trifft."""
    with contextlib.suppress(AttributeError, OSError):
        os.posix_fadvise(file.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)


class HashingWriter:
    """Leitet Schreibvorgänge weiter und zählt Bytes und SHA-256 mit."""

    def __init__(self, target: BinaryIO) -> None:
        self._target = target
        self._hash = hashlib.sha256()
        self.size = 0

    def write(self, data: bytes) -> int:
        self._target.write(data)
        self._hash.update(data)
        self.size += len(data)
        return len(data)

    def hexdigest(self) -> str:
        return self._hash.hexdigest()


def atomic_write(path: Path, produce: Callable[[BinaryIO], None], *, mode: int = 0o644) -> None:
    """Schreibt `path` über `path.tmp`; bei einem Fehler bleibt nichts Halbes liegen."""
    tmp = path.with_name(path.name + TMP_SUFFIX)
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "wb") as file:
            produce(file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    fsync_dir(path.parent)


def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o644) -> None:
    atomic_write(path, lambda file: file.write(data), mode=mode)


def iter_file(path: Path, *, uncached: bool = False) -> Iterator[bytes]:
    with path.open("rb") as file:
        if uncached:
            drop_cache(file)
        while chunk := file.read(_READ_SIZE):
            yield chunk


def sha256_file(path: Path, *, uncached: bool = False) -> str:
    digest = hashlib.sha256()
    for chunk in iter_file(path, uncached=uncached):
        digest.update(chunk)
    return digest.hexdigest()


def checksum_path(path: Path) -> Path:
    return path.with_name(path.name + CHECKSUM_SUFFIX)


def write_checksum(path: Path, digest: str) -> None:
    """Prüfsumme im Format von `sha256sum`, damit sie sich auch von Hand prüfen lässt."""
    atomic_write_bytes(checksum_path(path), f"{digest}  {path.name}\n".encode())


def read_checksum(path: Path) -> str | None:
    try:
        text = checksum_path(path).read_text(encoding="ascii")
    except OSError, UnicodeDecodeError:
        return None
    digest = text.split(maxsplit=1)[0] if text.strip() else ""
    return digest if len(digest) == 64 else None
