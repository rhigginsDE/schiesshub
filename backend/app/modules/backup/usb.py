"""Erkennung des Sicherungs-Sticks.

Der Stick gilt nur als vorhanden, wenn im Stick-Verzeichnis die Marker-Datei liegt. Auf dem
Server ist das Verzeichnis ein Mountpunkt, der ohne Stick leer ist; ohne Marker wird deshalb nie
geschrieben, sonst landete die „Sicherung“ still auf der internen Platte.
"""

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.modules.backup import fsutil

SNAPSHOT_DIR = "snapshots"
JOURNAL_DIR = "journal"


class UsbUnavailableError(Exception):
    """Der Stick fehlt oder ist nicht nutzbar. Die Meldung ist für Anwender gedacht."""


@dataclass(frozen=True, slots=True)
class UsbProbe:
    present: bool
    writable: bool
    free_bytes: int | None
    error: str | None = None


def probe(usb_dir: Path, marker: str) -> UsbProbe:
    """Prüft nur lesend (Marker, Schreibrecht, freier Platz), damit der Stick nicht verschleißt."""
    try:
        if not (usb_dir / marker).is_file():
            return UsbProbe(present=False, writable=False, free_bytes=None)
        writable = os.access(usb_dir, os.W_OK)
        free = shutil.disk_usage(usb_dir).free
    except OSError as exc:
        return UsbProbe(
            present=False, writable=False, free_bytes=None, error=f"Stick nicht lesbar: {exc}"
        )
    return UsbProbe(present=True, writable=writable, free_bytes=free)


def require_marker(usb_dir: Path, marker: str) -> None:
    """Letzte Prüfung unmittelbar vor jedem Schreibzugriff."""
    if not (usb_dir / marker).is_file():
        raise UsbUnavailableError("Kein Sicherungs-Stick gefunden.")


def ensure_dir(usb_dir: Path, marker: str, name: str) -> Path:
    require_marker(usb_dir, marker)
    path = usb_dir / name
    if not path.is_dir():
        path.mkdir()
        fsutil.fsync_dir(usb_dir)
    return path


def initialize(usb_dir: Path, marker: str) -> None:
    """Legt die Marker-Datei auf einem neuen Stick an."""
    if not usb_dir.is_dir():
        raise UsbUnavailableError("Das Verzeichnis für den Sicherungs-Stick gibt es nicht.")
    if (usb_dir / marker).exists():
        raise FileExistsError
    if not os.access(usb_dir, os.W_OK):
        raise UsbUnavailableError("Der Sicherungs-Stick ist nicht beschreibbar.")
    content = json.dumps(
        {"id": str(uuid.uuid4()), "initialized_at": datetime.now(UTC).isoformat()}
    ).encode()
    fsutil.atomic_write_bytes(usb_dir / marker, content)
