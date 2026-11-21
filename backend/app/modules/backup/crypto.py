"""Verschlüsselung der Sicherungen mit dem Sicherungspasswort.

Schlüssel
---------
Beim Setzen des Passworts entsteht ein zufälliger Datenschlüssel (32 Byte). Aus dem Passwort wird
mit Argon2id ein Schlüssel abgeleitet, der den Datenschlüssel mit AES-256-GCM einwickelt. Der
Server speichert unter ``data_dir/keys/backup-key.json`` den Datenschlüssel und den eingewickelten
Schlüsselkopf, aber nie das Passwort. So kann er ohne Eingabe weiter sichern; jede Sicherungsdatei
trägt den Schlüsselkopf mit, und auf einem neuen Server genügt das Passwort.

Schlüsselkopf (98 Byte, Zahlen Big-Endian)
------------------------------------------
::

    magic        8   b"SHUBBAK\\x00"
    version      1   1
    kdf          1   1 = Argon2id
    memory_kib   4   Speicherbedarf der Ableitung
    iterations   4
    lanes        4
    salt        16
    wrap_nonce  12
    wrapped_key 48   AES-256-GCM(KEK, wrap_nonce, Datenschlüssel, aad = Byte 0..49)

Verschlüsselte Sicherung (Endung ``.shb``)
------------------------------------------
::

    Schlüsselkopf   98
    chunk_size       4   Klartextgröße eines vollen Stücks
    nonce_prefix     7   zufällig je Datei
    Stück …              je: Länge (4) + AES-256-GCM-Chiffrat mit Tag
                         nonce = nonce_prefix || Zähler (4) || letztes (1 Byte: 0/1)
                         aad   = die 109 Byte Dateikopf

Das letzte Stück trägt die Markierung 1 (es darf leer sein). Fehlt es oder folgen danach noch
Daten, gilt die Datei als beschädigt. So bleiben große Abzüge beim Ver- und Entschlüsseln
stückweise im Speicher, und Abschneiden oder Vertauschen von Stücken fällt auf.

Verschlüsselte Mitschrift (Endung ``.shbj``, zeilenweise)
---------------------------------------------------------
::

    Zeile 1:  "SHBJ1 " + Base64(Schlüsselkopf)
    weitere:  Base64(nonce (12) || AES-256-GCM(Datenschlüssel, nonce, JSON-Zeile, aad = Kopf))

Jede Zeile ist für sich entschlüsselbar; eine abgerissene letzte Zeile wird übersprungen.
"""

import base64
import hashlib
import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from app.modules.backup import fsutil

MAGIC = b"SHUBBAK\x00"
FORMAT_VERSION = 1
KDF_ARGON2ID = 1
JOURNAL_PREFIX = b"SHBJ1 "

# Argon2id nach OWASP-Empfehlung; dauert auf einem Mini-PC rund 0,1 s.
DEFAULT_MEMORY_KIB = 64 * 1024
DEFAULT_ITERATIONS = 3
DEFAULT_LANES = 4
# Obergrenzen beim Lesen fremder Dateien, damit ein manipulierter Kopf den Server nicht lahmlegt.
MAX_MEMORY_KIB = 1024 * 1024
MAX_ITERATIONS = 20
MAX_LANES = 16

DEFAULT_CHUNK_SIZE = 1024 * 1024
MAX_CHUNK_SIZE = 64 * 1024 * 1024

_KEY_PREFIX = struct.Struct(">8sBBIII16s")  # wird als aad beim Einwickeln verwendet
_KEY_HEADER = struct.Struct(">8sBBIII16s12s48s")
_STREAM_HEADER = struct.Struct(">I7s")
_CHUNK_LENGTH = struct.Struct(">I")
KEY_HEADER_SIZE = _KEY_HEADER.size
FILE_HEADER_SIZE = KEY_HEADER_SIZE + _STREAM_HEADER.size
TAG_SIZE = 16

KEY_FILE_NAME = "backup-key.json"


class BackupCryptoError(Exception):
    """Basis der Fehler beim Entschlüsseln. Die Meldung ist für Anwender gedacht."""


class WrongPassphraseError(BackupCryptoError):
    def __init__(self) -> None:
        super().__init__("Das Sicherungspasswort ist falsch.")


class CorruptBackupError(BackupCryptoError):
    pass


@dataclass(frozen=True, slots=True)
class KdfParams:
    memory_kib: int = DEFAULT_MEMORY_KIB
    iterations: int = DEFAULT_ITERATIONS
    lanes: int = DEFAULT_LANES

    def derive(self, passphrase: str, salt: bytes) -> bytes:
        return Argon2id(
            salt=salt,
            length=32,
            iterations=self.iterations,
            lanes=self.lanes,
            memory_cost=self.memory_kib,
        ).derive(passphrase.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class BackupKey:
    """Datenschlüssel und sein mit dem Passwort eingewickelter Kopf."""

    data_key: bytes
    key_header: bytes

    @property
    def key_id(self) -> str:
        """Kurze Kennung, abgeleitet aus dem Kopf (verrät nichts über den Schlüssel)."""
        return hashlib.sha256(self.key_header).hexdigest()[:12]


def create_key(passphrase: str, params: KdfParams | None = None) -> BackupKey:
    params = params or KdfParams()
    data_key = AESGCM.generate_key(bit_length=256)
    salt = os.urandom(16)
    prefix = _KEY_PREFIX.pack(
        MAGIC,
        FORMAT_VERSION,
        KDF_ARGON2ID,
        params.memory_kib,
        params.iterations,
        params.lanes,
        salt,
    )
    wrap_nonce = os.urandom(12)
    wrapped = AESGCM(params.derive(passphrase, salt)).encrypt(wrap_nonce, data_key, prefix)
    return BackupKey(data_key=data_key, key_header=prefix + wrap_nonce + wrapped)


def unwrap_key(key_header: bytes, passphrase: str) -> BackupKey:
    """Prüft den Schlüsselkopf und packt den Datenschlüssel mit dem Passwort aus."""
    if len(key_header) != KEY_HEADER_SIZE:
        raise CorruptBackupError("Der Dateikopf ist unvollständig.")
    magic, version, kdf, memory_kib, iterations, lanes, salt, wrap_nonce, wrapped = (
        _KEY_HEADER.unpack(key_header)
    )
    if magic != MAGIC:
        raise CorruptBackupError("Das ist keine verschlüsselte Schiesshub-Sicherung.")
    if version != FORMAT_VERSION or kdf != KDF_ARGON2ID:
        raise CorruptBackupError(
            f"Diese Sicherung hat das Format {version}/{kdf}, das diese Version nicht lesen kann."
        )
    if not (
        8 <= memory_kib <= MAX_MEMORY_KIB
        and 1 <= iterations <= MAX_ITERATIONS
        and 1 <= lanes <= MAX_LANES
    ):
        raise CorruptBackupError("Der Dateikopf enthält unzulässige Parameter.")
    kek = KdfParams(memory_kib, iterations, lanes).derive(passphrase, salt)
    try:
        data_key = AESGCM(kek).decrypt(wrap_nonce, wrapped, key_header[: _KEY_PREFIX.size])
    except InvalidTag:
        raise WrongPassphraseError() from None
    return BackupKey(data_key=data_key, key_header=key_header)


# --- Schlüsseldatei auf dem Server ------------------------------------------------


def load_key(keys_dir: Path) -> BackupKey | None:
    path = keys_dir / KEY_FILE_NAME
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return BackupKey(
        data_key=base64.b64decode(data["data_key"]),
        key_header=base64.b64decode(data["key_header"]),
    )


def save_key(keys_dir: Path, key: BackupKey) -> None:
    keys_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(keys_dir, 0o700)
    payload = json.dumps(
        {
            "version": FORMAT_VERSION,
            "data_key": base64.b64encode(key.data_key).decode("ascii"),
            "key_header": base64.b64encode(key.key_header).decode("ascii"),
        }
    ).encode("utf-8")
    fsutil.atomic_write_bytes(keys_dir / KEY_FILE_NAME, payload, mode=0o600)


# --- Stückweise Verschlüsselung --------------------------------------------------


def _nonce(prefix: bytes, counter: int, last: bool) -> bytes:
    return prefix + struct.pack(">I", counter) + (b"\x01" if last else b"\x00")


class EncryptingWriter:
    """Dateiähnliches Objekt: verschlüsselt alles Geschriebene stückweise in `target`."""

    def __init__(
        self, target: BinaryIO, key: BackupKey, chunk_size: int = DEFAULT_CHUNK_SIZE
    ) -> None:
        self._target = target
        self._aead = AESGCM(key.data_key)
        self._chunk_size = chunk_size
        prefix = os.urandom(7)
        self._prefix = prefix
        self._header = key.key_header + _STREAM_HEADER.pack(chunk_size, prefix)
        self._buffer = bytearray()
        self._counter = 0
        self._closed = False
        target.write(self._header)

    def write(self, data: bytes) -> int:
        if self._closed:
            raise ValueError("Der Schreiber ist bereits geschlossen.")
        self._buffer.extend(data)
        # Strikt größer: Der Rest bleibt für das letzte Stück, das close() schreibt.
        while len(self._buffer) > self._chunk_size:
            self._emit(bytes(self._buffer[: self._chunk_size]), last=False)
            del self._buffer[: self._chunk_size]
        return len(data)

    def close(self) -> None:
        if not self._closed:
            self._emit(bytes(self._buffer), last=True)
            self._buffer.clear()
            self._closed = True

    def _emit(self, chunk: bytes, *, last: bool) -> None:
        ciphertext = self._aead.encrypt(
            _nonce(self._prefix, self._counter, last), chunk, self._header
        )
        self._target.write(_CHUNK_LENGTH.pack(len(ciphertext)))
        self._target.write(ciphertext)
        self._counter += 1


def read_key_header(source: BinaryIO) -> bytes:
    header = source.read(KEY_HEADER_SIZE)
    if len(header) < KEY_HEADER_SIZE or not header.startswith(MAGIC):
        raise CorruptBackupError("Das ist keine verschlüsselte Schiesshub-Sicherung.")
    return header


class DecryptingReader:
    """Dateiähnliches Objekt zum Lesen einer `.shb`-Datei.

    Den Schlüssel liefert entweder das Passwort (Wiederherstellung) oder der Server selbst.
    """

    def __init__(
        self, source: BinaryIO, *, passphrase: str | None = None, key: BackupKey | None = None
    ) -> None:
        if (passphrase is None) == (key is None):
            raise ValueError("Genau eines von passphrase oder key angeben.")
        self._source = source
        key_header = read_key_header(source)
        if passphrase is not None:
            key = unwrap_key(key_header, passphrase)
        elif key is not None and key.key_header != key_header:
            raise CorruptBackupError(
                "Diese Sicherung wurde mit einem anderen Sicherungspasswort verschlüsselt."
            )
        assert key is not None
        self.key = key
        stream_header = source.read(_STREAM_HEADER.size)
        if len(stream_header) < _STREAM_HEADER.size:
            raise CorruptBackupError("Der Dateikopf ist unvollständig.")
        self._chunk_size, self._prefix = _STREAM_HEADER.unpack(stream_header)
        if not 1 <= self._chunk_size <= MAX_CHUNK_SIZE:
            raise CorruptBackupError("Der Dateikopf enthält unzulässige Parameter.")
        self._header = key_header + stream_header
        self._aead = AESGCM(key.data_key)
        self._buffer = bytearray()
        self._counter = 0
        self._finished = False

    def read(self, size: int = -1) -> bytes:
        while not self._finished and (size < 0 or len(self._buffer) < size):
            self._next_chunk()
        if size < 0:
            size = len(self._buffer)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def finish(self) -> None:
        """Liest bis zum Ende und stellt sicher, dass die Datei vollständig ist."""
        while not self._finished:
            self._next_chunk()
        self._buffer.clear()

    def _next_chunk(self) -> None:
        raw_length = self._source.read(_CHUNK_LENGTH.size)
        if len(raw_length) < _CHUNK_LENGTH.size:
            raise CorruptBackupError("Die Sicherung ist unvollständig (abgeschnitten).")
        (length,) = _CHUNK_LENGTH.unpack(raw_length)
        if not TAG_SIZE <= length <= self._chunk_size + TAG_SIZE:
            raise CorruptBackupError("Die Sicherung ist beschädigt.")
        ciphertext = self._source.read(length)
        if len(ciphertext) < length:
            raise CorruptBackupError("Die Sicherung ist unvollständig (abgeschnitten).")
        for last in (False, True):
            try:
                chunk = self._aead.decrypt(
                    _nonce(self._prefix, self._counter, last), ciphertext, self._header
                )
            except InvalidTag:
                continue
            break
        else:
            raise CorruptBackupError("Die Sicherung ist beschädigt (Prüfung fehlgeschlagen).")
        self._counter += 1
        self._buffer.extend(chunk)
        if last:
            if self._source.read(1):
                raise CorruptBackupError("Hinter dem Ende der Sicherung stehen weitere Daten.")
            self._finished = True


# --- Zeilenweise Verschlüsselung der Mitschrift -----------------------------------


def journal_header_line(key: BackupKey) -> bytes:
    return JOURNAL_PREFIX + base64.b64encode(key.key_header) + b"\n"


def parse_journal_header_line(line: bytes) -> bytes:
    if not line.startswith(JOURNAL_PREFIX):
        raise CorruptBackupError("Das ist keine verschlüsselte Schiesshub-Mitschrift.")
    try:
        return base64.b64decode(line[len(JOURNAL_PREFIX) :].strip(), validate=True)
    except ValueError:
        raise CorruptBackupError("Der Kopf der Mitschrift ist beschädigt.") from None


def encrypt_line(key: BackupKey, plaintext: bytes) -> bytes:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key.data_key).encrypt(nonce, plaintext, key.key_header)
    return base64.b64encode(nonce + ciphertext) + b"\n"


def decrypt_line(key: BackupKey, line: bytes) -> bytes | None:
    """Entschlüsselt eine Zeile; `None`, wenn sie unvollständig oder beschädigt ist."""
    try:
        raw = base64.b64decode(line.strip(), validate=True)
    except ValueError:
        return None
    if len(raw) < 12 + TAG_SIZE:
        return None
    try:
        return AESGCM(key.data_key).decrypt(raw[:12], raw[12:], key.key_header)
    except InvalidTag:
        return None
