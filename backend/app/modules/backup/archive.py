"""Sicherungsarchiv: Datenbank-Abzug, Schlüsselverzeichnis und Manifest in einem tar-Strom.

Inhalt (in dieser Reihenfolge)::

    manifest.json     Format, Zeitpunkt, Prüfsumme und Größe des Abzugs, Liste der Schlüsseldateien
    database.dump     pg_dump im Custom-Format
    keys/…            Inhalt von data_dir/keys (Feldschlüssel, Sicherungsschlüssel)

Das Archiv wird als Strom geschrieben und gelesen (`tarfile` im Modus `w|` / `r|`), damit es
direkt durch die Verschlüsselung laufen kann und nie ganz im Speicher liegt.
"""

import hashlib
import io
import json
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from app.modules.backup import fsutil

ARCHIVE_FORMAT = "schiesshub-backup"
ARCHIVE_VERSION = 1
MANIFEST_NAME = "manifest.json"
DATABASE_NAME = "database.dump"
KEYS_PREFIX = "keys"


class ArchiveError(Exception):
    """Das Archiv ist unvollständig oder passt nicht zu seinem Manifest."""


@dataclass(frozen=True, slots=True)
class ArchiveContents:
    manifest: dict[str, Any]
    entries: list[str]
    database_file: Path | None
    keys_dir: Path | None
    database_sha256_ok: bool


def key_files(keys_dir: Path) -> list[Path]:
    if not keys_dir.is_dir():
        return []
    return sorted(
        path
        for path in keys_dir.rglob("*")
        if path.is_file() and not path.name.endswith(fsutil.TMP_SUFFIX)
    )


def build_manifest(
    *,
    created_at: str,
    app_version: str,
    pg_dump_version: str,
    dump: Path,
    dump_sha256: str,
    keys_dir: Path,
) -> dict[str, Any]:
    return {
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "created_at": created_at,
        "app_version": app_version,
        "database": {
            "file": DATABASE_NAME,
            "sha256": dump_sha256,
            "size_bytes": dump.stat().st_size,
            "pg_dump": pg_dump_version,
        },
        "keys": [path.relative_to(keys_dir).as_posix() for path in key_files(keys_dir)],
    }


def _add_file(archive: tarfile.TarFile, name: str, source: BinaryIO, size: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = 0o600
    info.mtime = int(time.time())
    archive.addfile(info, source)


def write_archive(out: Any, manifest: dict[str, Any], dump: Path, keys_dir: Path) -> None:
    """Schreibt das Archiv in das dateiähnliche Objekt `out` (nur `write` nötig)."""
    with tarfile.open(fileobj=out, mode="w|", format=tarfile.PAX_FORMAT) as archive:
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        _add_file(archive, MANIFEST_NAME, io.BytesIO(manifest_bytes), len(manifest_bytes))
        with dump.open("rb") as file:
            _add_file(archive, DATABASE_NAME, file, dump.stat().st_size)
        for path in key_files(keys_dir):
            relative = path.relative_to(keys_dir).as_posix()
            with path.open("rb") as file:
                _add_file(archive, f"{KEYS_PREFIX}/{relative}", file, path.stat().st_size)


def _allowed(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    return name in (MANIFEST_NAME, DATABASE_NAME) or (
        len(path.parts) > 1 and path.parts[0] == KEYS_PREFIX
    )


def read_archive(source: Any, target_dir: Path | None) -> ArchiveContents:
    """Liest ein Archiv aus `source` (nur `read` nötig).

    Mit `target_dir` werden Abzug und Schlüssel dorthin entpackt; ohne wird nur geprüft
    (Prüfsumme des Abzugs, Liste der Einträge).
    """
    manifest: dict[str, Any] | None = None
    entries: list[str] = []
    digest = hashlib.sha256()
    database_file: Path | None = None
    keys_dir: Path | None = None
    try:
        with tarfile.open(fileobj=source, mode="r|") as archive:
            for member in archive:
                if not member.isfile() or not _allowed(member.name):
                    raise ArchiveError(f"Unerwarteter Eintrag im Archiv: {member.name}")
                entries.append(member.name)
                extracted = archive.extractfile(member)
                assert extracted is not None
                if member.name == MANIFEST_NAME:
                    manifest = json.loads(extracted.read().decode("utf-8"))
                    continue
                target = target_dir / member.name if target_dir is not None else None
                if target is not None:
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                out = target.open("wb") if target is not None else None
                try:
                    while chunk := extracted.read(1024 * 1024):
                        if member.name == DATABASE_NAME:
                            digest.update(chunk)
                        if out is not None:
                            out.write(chunk)
                finally:
                    if out is not None:
                        out.close()
                if target is not None:
                    target.chmod(0o600)
                if member.name == DATABASE_NAME:
                    database_file = target
                elif target_dir is not None:
                    keys_dir = target_dir / KEYS_PREFIX
    except tarfile.TarError as exc:
        raise ArchiveError(f"Das Archiv ist beschädigt: {exc}") from exc
    if manifest is None or manifest.get("format") != ARCHIVE_FORMAT:
        raise ArchiveError("Im Archiv fehlt das Manifest einer Schiesshub-Sicherung.")
    if DATABASE_NAME not in entries:
        raise ArchiveError("Im Archiv fehlt der Datenbank-Abzug.")
    expected = manifest.get("database", {}).get("sha256")
    return ArchiveContents(
        manifest=manifest,
        entries=entries,
        database_file=database_file,
        keys_dir=keys_dir,
        database_sha256_ok=digest.hexdigest() == expected,
    )
