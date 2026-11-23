"""Zufällige Token und Codes, ihre Hashes und das Hashen der PINs (Argon2id)."""

import asyncio
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Kopplungscodes: ohne leicht verwechselbare Zeichen (0/O, 1/I/L), gut abzutippen.
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_CODE_LENGTH = 10

_hasher = PasswordHasher()  # Argon2id mit den Standardparametern der Bibliothek
# Vergleichswert für unbekannte Benutzer, damit jede falsche Anmeldung gleich lange dauert.
_dummy_hash = _hasher.hash("0000")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_pairing_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def normalize_pairing_code(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def token_hash(token: str) -> str:
    """Token haben genug Zufall; ein schneller Hash genügt und erlaubt die Suche per Index."""
    return hashlib.sha256(token.encode()).hexdigest()


async def hash_pin(pin: str) -> str:
    return await asyncio.to_thread(_hasher.hash, pin)


async def verify_pin(pin_hash: str | None, pin: str) -> bool:
    """Prüft die PIN. Ohne Hash (unbekannter Benutzer) wird gegen einen Platzhalter gerechnet."""

    def verify() -> bool:
        try:
            return _hasher.verify(pin_hash or _dummy_hash, pin) and pin_hash is not None
        except VerificationError, InvalidHashError:
            return False

    return await asyncio.to_thread(verify)
