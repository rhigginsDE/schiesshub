"""Dateiformat der Verschlüsselung und der Mitschrift, ohne Datenbank."""

import io
import os
from pathlib import Path

import pytest

from app.modules.backup import crypto, journal

# Schnelle Ableitung für Unit-Tests; das Format trägt die Parameter im Kopf mit.
FAST = crypto.KdfParams(memory_kib=1024, iterations=1, lanes=1)


def _encrypt(data: bytes, key: crypto.BackupKey, chunk_size: int) -> bytes:
    out = io.BytesIO()
    writer = crypto.EncryptingWriter(out, key, chunk_size=chunk_size)
    for start in range(0, len(data), 1000):
        writer.write(data[start : start + 1000])
    writer.close()
    return out.getvalue()


def _decrypt(blob: bytes, passphrase: str) -> bytes:
    reader = crypto.DecryptingReader(io.BytesIO(blob), passphrase=passphrase)
    data = reader.read()
    reader.finish()
    return data


@pytest.mark.parametrize("size", [0, 1, 4096, 4097, 50_000])
def test_roundtrip_in_chunks(size: int) -> None:
    key = crypto.create_key("ein langes Passwort", FAST)
    data = os.urandom(size)
    blob = _encrypt(data, key, chunk_size=4096)
    assert blob.startswith(crypto.MAGIC)
    assert _decrypt(blob, "ein langes Passwort") == data


def test_wrong_passphrase_fails_cleanly() -> None:
    key = crypto.create_key("ein langes Passwort", FAST)
    blob = _encrypt(b"geheim", key, chunk_size=4096)
    with pytest.raises(crypto.WrongPassphraseError, match="Sicherungspasswort ist falsch"):
        _decrypt(blob, "ein falsches Passwort")


def test_truncated_file_is_detected() -> None:
    key = crypto.create_key("ein langes Passwort", FAST)
    blob = _encrypt(os.urandom(20_000), key, chunk_size=4096)
    # Genau an einer Stückgrenze abgeschnitten: Ohne die Markierung „letztes Stück“ fiele das
    # nicht auf.
    chunk_bytes = 4 + 4096 + crypto.TAG_SIZE
    cut = crypto.FILE_HEADER_SIZE + 2 * chunk_bytes
    with pytest.raises(crypto.CorruptBackupError, match="abgeschnitten"):
        _decrypt(blob[:cut], "ein langes Passwort")


def test_tampering_and_trailing_data_are_detected() -> None:
    key = crypto.create_key("ein langes Passwort", FAST)
    blob = bytearray(_encrypt(os.urandom(10_000), key, chunk_size=4096))
    with pytest.raises(crypto.CorruptBackupError, match="weitere Daten"):
        _decrypt(bytes(blob) + b"x", "ein langes Passwort")
    blob[crypto.FILE_HEADER_SIZE + 100] ^= 0x01
    with pytest.raises(crypto.CorruptBackupError, match="beschädigt"):
        _decrypt(bytes(blob), "ein langes Passwort")


def test_server_key_must_match_header() -> None:
    blob = _encrypt(b"x", crypto.create_key("ein langes Passwort", FAST), chunk_size=16)
    other = crypto.create_key("ein langes Passwort", FAST)
    with pytest.raises(crypto.CorruptBackupError, match="anderen Sicherungspasswort"):
        crypto.DecryptingReader(io.BytesIO(blob), key=other)


def test_key_file_roundtrip(tmp_path: Path) -> None:
    key = crypto.create_key("ein langes Passwort", FAST)
    crypto.save_key(tmp_path / "keys", key)
    assert crypto.load_key(tmp_path / "keys") == key
    assert (tmp_path / "keys" / crypto.KEY_FILE_NAME).stat().st_mode & 0o777 == 0o600
    assert b"ein langes Passwort" not in (tmp_path / "keys" / crypto.KEY_FILE_NAME).read_bytes()


# --- Mitschrift ---------------------------------------------------------------------


def test_journal_survives_torn_last_line(tmp_path: Path) -> None:
    log = journal.Journal(tmp_path)
    log.open()
    log.append({"n": 1})
    log.append({"n": 2})
    segment = log.segment_paths()[0]
    # Stromausfall mitten im Schreiben: halbe Zeile ohne Zeilenende.
    with segment.open("ab") as file:
        file.write(b'{"at":"2026-11-21T10:00:00+00:00","record":{"n":3')

    reopened = journal.Journal(tmp_path)
    reopened.open()
    assert reopened.append({"n": 4}) == 3
    entries = journal.read_entries(segment)
    assert [entry.seq for entry in entries] == [1, 2, 3]
    assert b'"n":4' in entries[-1].line


def test_journal_rejects_modified_lines(tmp_path: Path) -> None:
    log = journal.Journal(tmp_path)
    log.open()
    log.append({"ringe": 95})
    segment = log.segment_paths()[0]
    segment.write_bytes(segment.read_bytes().replace(b"95", b"99"))
    assert journal.read_entries(segment) == []


def test_encrypted_usb_journal_skips_torn_line(tmp_path: Path) -> None:
    key = crypto.create_key("ein langes Passwort", FAST)
    log = journal.Journal(tmp_path / "local")
    log.open()
    for n in range(3):
        log.append({"n": n})
    entries = journal.read_entries(log.segment_paths()[0])
    usb_file = tmp_path / "usb.shbj"
    journal.append_usb_file(usb_file, entries[:2], key)
    # Abgerissene letzte Zeile auf dem Stick.
    with usb_file.open("ab") as file:
        file.write(crypto.encrypt_line(key, entries[2].line)[:20])
    assert [e.seq for e in journal.read_usb_file(usb_file, key)] == [1, 2]

    # Weiterschreiben beginnt auf einer neuen Zeile; die kaputte Zeile bleibt die einzige Lücke.
    journal.append_usb_file(usb_file, entries[2:], key)
    assert [e.seq for e in journal.read_usb_file(usb_file, key)] == [1, 2, 3]
    assert [e.seq for e in journal.read_journal_file(usb_file, "ein langes Passwort")] == [1, 2, 3]
    with pytest.raises(crypto.WrongPassphraseError):
        journal.read_journal_file(usb_file, "ein falsches Passwort")
    assert b'"n"' not in usb_file.read_bytes()
