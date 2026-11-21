"""Feldverschlüsselung: Schlüsseldatei, Ver-/Entschlüsseln, Rotation, Typ für SQLAlchemy."""

import json
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core import crypto
from app.core.crypto import (
    CryptoError,
    DecryptionError,
    EncryptedText,
    FieldCipher,
    KeyStoreError,
    key_file_path,
    load_keyring,
    rotate_key,
    setup_field_cipher,
)


@pytest.fixture
def keys_dir(tmp_path: Path) -> Path:
    return tmp_path / "data" / "keys"


@pytest.fixture
def cipher(keys_dir: Path) -> FieldCipher:
    return FieldCipher(load_keyring(keys_dir, create=True))


@pytest.fixture
def app_cipher(keys_dir: Path) -> Iterator[FieldCipher]:
    """Setzt den anwendungsweiten Cipher mit temporärem Schlüssel und räumt danach auf."""
    yield setup_field_cipher(keys_dir, create=True)
    crypto.set_field_cipher(None)


# --- Schlüsseldatei ----------------------------------------------------------


def test_first_start_creates_key_file_with_strict_permissions(keys_dir: Path) -> None:
    ring = load_keyring(keys_dir, create=True)

    path = key_file_path(keys_dir)
    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["format"] == 1
    assert content["active"] == ring.active_id
    assert set(content["keys"]) == {ring.active_id}
    assert set(content["keys"][ring.active_id]) == {"key", "created_at"}
    assert len(ring.keys[ring.active_id]) == 32
    # Kein Rest der atomaren Schreibweise.
    assert sorted(p.name for p in keys_dir.iterdir()) == ["field-keys.json"]


def test_second_start_loads_the_same_key(keys_dir: Path) -> None:
    first = load_keyring(keys_dir, create=True)
    second = load_keyring(keys_dir, create=True)

    assert first == second


def test_missing_key_file_is_an_error_when_data_exists(keys_dir: Path) -> None:
    with pytest.raises(KeyStoreError, match="fehlt, aber es gibt bereits verschlüsselte Daten"):
        load_keyring(keys_dir, create=False)
    assert not keys_dir.exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{kaputt", "kein gültiges JSON"),
        ('{"format": 2, "active": "x", "keys": {}}', "unbekanntes Format"),
        ('{"format": 1, "active": "x", "keys": {}}', "enthält keine Schlüssel"),
        (
            '{"format": 1, "active": "zz", "keys": {"zz": {"key": "AA=="}}}',
            "ungültige Schlüssel-ID",
        ),
        ('{"format": 1, "active": "0a0b0c0d", "keys": {"0a0b0c0d": {}}}', "beschädigt"),
        (
            '{"format": 1, "active": "0a0b0c0d", "keys": {"0a0b0c0d": {"key": "nicht base64!"}}}',
            "beschädigt",
        ),
        ('{"format": 1, "active": "0a0b0c0d", "keys": {"0a0b0c0d": {"key": "AAAA"}}}', "256 Bit"),
    ],
)
def test_broken_key_file_is_a_clear_error(keys_dir: Path, content: str, message: str) -> None:
    keys_dir.mkdir(parents=True)
    key_file_path(keys_dir).write_text(content, encoding="utf-8")

    with pytest.raises(KeyStoreError, match=message):
        load_keyring(keys_dir, create=True)


def test_active_key_must_exist(keys_dir: Path) -> None:
    ring = load_keyring(keys_dir, create=True)
    path = key_file_path(keys_dir)
    content = json.loads(path.read_text(encoding="utf-8"))
    content["active"] = "ffffffff"
    path.write_text(json.dumps(content), encoding="utf-8")

    with pytest.raises(KeyStoreError, match="aktive Schlüssel 'ffffffff'"):
        load_keyring(keys_dir, create=False)
    assert ring.active_id != "ffffffff"


def test_keys_never_appear_in_repr_or_errors(keys_dir: Path) -> None:
    ring = load_keyring(keys_dir, create=True)
    cipher = FieldCipher(ring)
    encoded_key = json.loads(key_file_path(keys_dir).read_text(encoding="utf-8"))["keys"][
        ring.active_id
    ]["key"]

    for shown in (repr(ring), str(ring), repr(cipher)):
        assert encoded_key not in shown
        assert repr(ring.keys[ring.active_id]) not in shown
    with pytest.raises(DecryptionError) as error:
        cipher.decrypt(b"\x01" + bytes(40))
    assert encoded_key not in str(error.value)


# --- Ver- und Entschlüsseln --------------------------------------------------


@pytest.mark.parametrize("plaintext", ["Markus Brandt", "Jürgen Köhler-Weiß", "", "李小龍 🎯"])
def test_roundtrip(cipher: FieldCipher, plaintext: str) -> None:
    value = cipher.encrypt(plaintext)

    assert isinstance(value, bytes)
    assert cipher.decrypt(value) == plaintext
    assert plaintext.encode("utf-8") not in value or plaintext == ""


def test_value_layout_carries_version_and_key_id(cipher: FieldCipher) -> None:
    value = cipher.encrypt("Markus Brandt")

    assert value[0] == 1
    assert FieldCipher.key_id_of(value) == cipher.active_key_id
    # Version + Schlüssel-ID + Nonce + Text + Tag.
    assert len(value) == 1 + 4 + 12 + len("Markus Brandt") + 16


def test_same_plaintext_gives_different_ciphertexts(cipher: FieldCipher) -> None:
    values = {cipher.encrypt("Markus Brandt") for _ in range(20)}

    assert len(values) == 20
    assert {cipher.decrypt(value) for value in values} == {"Markus Brandt"}


@pytest.mark.parametrize(
    "position",
    [
        0,  # Version
        2,  # Schlüssel-ID
        7,  # Nonce
        20,  # Chiffrat
        -1,  # Tag
    ],
)
def test_tampering_is_detected(cipher: FieldCipher, position: int) -> None:
    value = bytearray(cipher.encrypt("Markus Brandt"))
    value[position] ^= 0x01

    with pytest.raises(DecryptionError):
        cipher.decrypt(bytes(value))


def test_truncated_value_is_detected(cipher: FieldCipher) -> None:
    value = cipher.encrypt("Markus Brandt")

    with pytest.raises(DecryptionError, match="zu kurz"):
        cipher.decrypt(value[:20])
    with pytest.raises(DecryptionError, match="verändert oder ist beschädigt"):
        cipher.decrypt(value[:-1])


def test_value_from_another_key_file_is_rejected(cipher: FieldCipher, tmp_path: Path) -> None:
    other = FieldCipher(load_keyring(tmp_path / "andere", create=True))

    with pytest.raises(DecryptionError, match="nicht vorhanden"):
        other.decrypt(cipher.encrypt("Markus Brandt"))


def test_key_rotation_reads_old_and_writes_new(keys_dir: Path) -> None:
    old_cipher = FieldCipher(load_keyring(keys_dir, create=True))
    old_value = old_cipher.encrypt("Markus Brandt")

    rotated = rotate_key(keys_dir)
    new_cipher = FieldCipher(load_keyring(keys_dir, create=False))
    new_value = new_cipher.encrypt("Markus Brandt")

    assert rotated.active_id != old_cipher.active_key_id
    assert new_cipher.active_key_id == rotated.active_id
    assert len(rotated.keys) == 2
    # Alte Werte bleiben lesbar, neue entstehen mit dem neuen Schlüssel.
    assert new_cipher.decrypt(old_value) == "Markus Brandt"
    assert FieldCipher.key_id_of(old_value) == old_cipher.active_key_id
    assert FieldCipher.key_id_of(new_value) == rotated.active_id
    assert new_cipher.decrypt(new_value) == "Markus Brandt"
    # Der alte Stand kennt den neuen Schlüssel nicht.
    with pytest.raises(DecryptionError):
        old_cipher.decrypt(new_value)
    assert stat.S_IMODE(key_file_path(keys_dir).stat().st_mode) == 0o600


# --- SQLAlchemy-Typ ----------------------------------------------------------


def test_encrypted_text_without_cipher_is_an_error() -> None:
    crypto.set_field_cipher(None)

    with pytest.raises(CryptoError, match="nicht eingerichtet"):
        crypto.get_field_cipher()


async def test_encrypted_text_stores_no_plaintext_in_the_database(
    engine: AsyncEngine, app_cipher: FieldCipher
) -> None:
    table = Table(
        "crypto_probe",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("secret", EncryptedText),
        prefixes=["TEMPORARY"],
    )
    async with engine.connect() as connection:
        await connection.run_sync(table.create)
        await connection.execute(
            insert(table), [{"id": 1, "secret": "Jürgen Köhler"}, {"id": 2, "secret": None}]
        )

        decrypted = (await connection.execute(select(table.c.secret).order_by(table.c.id))).all()
        raw = (
            await connection.execute(text("SELECT secret FROM crypto_probe WHERE id = 1"))
        ).scalar_one()
        as_text = (
            await connection.execute(text("SELECT crypto_probe::text FROM crypto_probe"))
        ).scalars()

        assert [row.secret for row in decrypted] == ["Jürgen Köhler", None]
        assert app_cipher.decrypt(raw) == "Jürgen Köhler"
        assert "Köhler".encode() not in raw
        assert all("Köhler" not in row and "hler" not in row for row in as_text)
