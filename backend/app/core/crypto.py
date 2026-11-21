"""Feldverschlüsselung für personenbezogene Daten (AES-256-GCM).

Aufbau eines verschlüsselten Werts (Bytes, in der Datenbank als BYTEA):

    Version (1 Byte, 0x01) · Schlüssel-ID (4 Byte) · Nonce (12 Byte) · Chiffrat mit Tag

Version und Schlüssel-ID sind als zusätzliche Daten (AAD) mit authentifiziert; wer sie ändert,
macht den Wert unlesbar. Die Schlüssel-ID erlaubt einen Schlüsselwechsel: Gelesen wird mit dem
Schlüssel, dessen ID im Wert steht, geschrieben immer mit dem aktiven Schlüssel.

Die Schlüssel liegen außerhalb der Datenbank in `<data_dir>/keys/field-keys.json`:

    {
      "format": 1,
      "active": "1a2b3c4d",
      "keys": {"1a2b3c4d": {"key": "<32 Byte, Base64>", "created_at": "2026-11-21T…+00:00"}}
    }

Verzeichnis 0700, Datei 0600. Schlüssel werden nie protokolliert und erscheinen in keiner
Fehlermeldung.
"""

import base64
import binascii
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import LargeBinary
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

KEY_FILE_NAME = "field-keys.json"
KEY_FILE_FORMAT = 1
VALUE_VERSION = 1
KEY_BYTES = 32
KEY_ID_BYTES = 4
NONCE_BYTES = 12
TAG_BYTES = 16
_HEADER_BYTES = 1 + KEY_ID_BYTES


class CryptoError(Exception):
    """Oberklasse aller Fehler der Feldverschlüsselung. Meldungen sind für Menschen gedacht."""


class KeyStoreError(CryptoError):
    """Schlüsseldatei fehlt, ist unlesbar oder enthält ungültige Schlüssel."""


class DecryptionError(CryptoError):
    """Ein gespeicherter Wert lässt sich nicht entschlüsseln (manipuliert, beschädigt, fremd)."""


def key_file_path(keys_dir: Path) -> Path:
    return keys_dir / KEY_FILE_NAME


@dataclass(frozen=True, slots=True)
class KeyRing:
    """Alle bekannten Schlüssel nach ID, dazu die ID des Schlüssels für neue Werte."""

    active_id: str
    keys: dict[str, bytes]

    def __repr__(self) -> str:  # Schlüssel nie in Tracebacks oder Logs zeigen.
        return f"KeyRing(active_id={self.active_id!r}, key_ids={sorted(self.keys)!r})"


# --- Schlüsseldatei ----------------------------------------------------------


def _new_key_id(existing: dict[str, bytes]) -> str:
    while True:
        key_id = secrets.token_hex(KEY_ID_BYTES)
        if key_id not in existing:
            return key_id


def _parse_key_file(path: Path) -> KeyRing:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise KeyStoreError(f"Die Schlüsseldatei {path} ist nicht lesbar: {exc.strerror}.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KeyStoreError(
            f"Die Schlüsseldatei {path} ist beschädigt (kein gültiges JSON)."
        ) from exc

    if not isinstance(raw, dict) or raw.get("format") != KEY_FILE_FORMAT:
        raise KeyStoreError(
            f"Die Schlüsseldatei {path} hat ein unbekanntes Format (erwartet: {KEY_FILE_FORMAT})."
        )
    entries = raw.get("keys")
    active = raw.get("active")
    if not isinstance(entries, dict) or not entries:
        raise KeyStoreError(f"Die Schlüsseldatei {path} enthält keine Schlüssel.")
    keys: dict[str, bytes] = {}
    for key_id, entry in entries.items():
        if not (isinstance(key_id, str) and len(key_id) == 2 * KEY_ID_BYTES):
            raise KeyStoreError(f"Die Schlüsseldatei {path} enthält eine ungültige Schlüssel-ID.")
        try:
            bytes.fromhex(key_id)
            key = base64.b64decode(entry["key"], validate=True)
        except (ValueError, TypeError, KeyError, binascii.Error) as exc:
            raise KeyStoreError(
                f"Der Schlüssel {key_id} in {path} ist beschädigt oder unvollständig."
            ) from exc
        if len(key) != KEY_BYTES:
            raise KeyStoreError(f"Der Schlüssel {key_id} in {path} hat nicht die Länge 256 Bit.")
        keys[key_id] = key
    if active not in keys:
        raise KeyStoreError(
            f"Der aktive Schlüssel {active!r} ist in der Schlüsseldatei {path} nicht vorhanden."
        )
    return KeyRing(active_id=active, keys=keys)


def _write_key_file(path: Path, ring: KeyRing, created: dict[str, str]) -> None:
    """Schreibt die Datei atomar (temporäre Datei, dann Umbenennen) mit Rechten 0600."""
    content: dict[str, Any] = {
        "format": KEY_FILE_FORMAT,
        "active": ring.active_id,
        "keys": {
            key_id: {"key": base64.b64encode(key).decode("ascii"), "created_at": created[key_id]}
            for key_id, key in ring.keys.items()
        },
    }
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(content, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _created_dates(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key_id: str(entry.get("created_at", "")) for key_id, entry in raw["keys"].items()}


def _ensure_keys_dir(keys_dir: Path) -> None:
    keys_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(keys_dir, 0o700)


def load_keyring(keys_dir: Path, *, create: bool) -> KeyRing:
    """Lädt die Schlüssel. Fehlt die Datei, wird sie nur mit `create=True` neu erzeugt.

    `create=False` ist für den Fall gedacht, dass schon verschlüsselte Daten existieren: Dann wäre
    ein neuer Schlüssel nutzlos, und die fehlende Datei muss aus der Sicherung zurückkommen.
    """
    path = key_file_path(keys_dir)
    if path.exists():
        return _parse_key_file(path)
    if not create:
        raise KeyStoreError(
            f"Die Schlüsseldatei {path} fehlt, aber es gibt bereits verschlüsselte Daten. "
            "Bitte die Datei aus der Sicherung wiederherstellen."
        )
    _ensure_keys_dir(keys_dir)
    key_id = secrets.token_hex(KEY_ID_BYTES)
    ring = KeyRing(active_id=key_id, keys={key_id: AESGCM.generate_key(bit_length=256)})
    _write_key_file(path, ring, {key_id: datetime.now(UTC).isoformat()})
    return ring


def rotate_key(keys_dir: Path) -> KeyRing:
    """Legt einen neuen Schlüssel an und macht ihn aktiv. Alte Schlüssel bleiben zum Lesen."""
    path = key_file_path(keys_dir)
    ring = _parse_key_file(path)
    created = _created_dates(path)
    key_id = _new_key_id(ring.keys)
    created[key_id] = datetime.now(UTC).isoformat()
    rotated = KeyRing(
        active_id=key_id, keys={**ring.keys, key_id: AESGCM.generate_key(bit_length=256)}
    )
    _write_key_file(path, rotated, created)
    return rotated


# --- Ver- und Entschlüsseln --------------------------------------------------


class FieldCipher:
    """Verschlüsselt Texte mit dem aktiven Schlüssel und entschlüsselt mit jedem bekannten."""

    def __init__(self, ring: KeyRing) -> None:
        self._active_id = ring.active_id
        self._active = AESGCM(ring.keys[ring.active_id])
        self._by_id = {bytes.fromhex(key_id): AESGCM(key) for key_id, key in ring.keys.items()}

    def __repr__(self) -> str:
        return f"FieldCipher(active_id={self._active_id!r})"

    @property
    def active_key_id(self) -> str:
        return self._active_id

    def encrypt(self, plaintext: str) -> bytes:
        header = bytes([VALUE_VERSION]) + bytes.fromhex(self._active_id)
        nonce = os.urandom(NONCE_BYTES)
        return header + nonce + self._active.encrypt(nonce, plaintext.encode("utf-8"), header)

    def decrypt(self, value: bytes) -> str:
        if len(value) < _HEADER_BYTES + NONCE_BYTES + TAG_BYTES:
            raise DecryptionError("Der verschlüsselte Wert ist zu kurz und damit beschädigt.")
        if value[0] != VALUE_VERSION:
            raise DecryptionError(
                f"Der verschlüsselte Wert hat eine unbekannte Version ({value[0]})."
            )
        header = value[:_HEADER_BYTES]
        key_id = header[1:]
        aead = self._by_id.get(key_id)
        if aead is None:
            raise DecryptionError(
                f"Der Schlüssel {key_id.hex()} für diesen Wert ist nicht vorhanden."
            )
        nonce = value[_HEADER_BYTES : _HEADER_BYTES + NONCE_BYTES]
        try:
            plaintext = aead.decrypt(nonce, value[_HEADER_BYTES + NONCE_BYTES :], header)
        except InvalidTag as exc:
            raise DecryptionError(
                "Der verschlüsselte Wert wurde verändert oder ist beschädigt."
            ) from exc
        return plaintext.decode("utf-8")

    @staticmethod
    def key_id_of(value: bytes) -> str:
        """ID des Schlüssels, mit dem ein Wert verschlüsselt ist (für eine Neuverschlüsselung)."""
        return value[1:_HEADER_BYTES].hex()


# --- Anwendungsweiter Cipher und SQLAlchemy-Typ -------------------------------

_cipher: FieldCipher | None = None


def set_field_cipher(cipher: FieldCipher | None) -> None:
    """Setzt den Cipher für `EncryptedText`. Läuft beim Start (Modul `teilnehmer`) und in Tests."""
    global _cipher
    _cipher = cipher


def get_field_cipher() -> FieldCipher:
    if _cipher is None:
        raise CryptoError(
            "Die Feldverschlüsselung ist nicht eingerichtet; der Schlüssel wurde nicht geladen."
        )
    return _cipher


def setup_field_cipher(keys_dir: Path, *, create: bool) -> FieldCipher:
    """Lädt oder erzeugt die Schlüssel und setzt den anwendungsweiten Cipher."""
    cipher = FieldCipher(load_keyring(keys_dir, create=create))
    set_field_cipher(cipher)
    return cipher


class EncryptedText(TypeDecorator[str]):
    """Text, der transparent mit dem anwendungsweiten `FieldCipher` verschlüsselt wird.

    In SQL sind die Werte nicht vergleichbar (jede Verschlüsselung ergibt ein anderes Chiffrat);
    gesucht wird deshalb im Arbeitsspeicher.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        return get_field_cipher().encrypt(value)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return get_field_cipher().decrypt(bytes(value))
