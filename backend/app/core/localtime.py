"""Ortszeit: Zeitpunkte speichert der Server in UTC, Listen und Anzeige zeigen sie in Ortszeit.

Die Zeitzone ist eine Einstellung je Turnier (`settings.timezone`, IANA-Name wie
„Europe/Berlin“). Fehlt sie (ältere Turniere) oder ist sie unbekannt, gilt `DEFAULT_TIMEZONE`.
"""

from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Europe/Berlin"
# Schlüssel in `tournament.settings`.
TIMEZONE_SETTING = "timezone"


@lru_cache(maxsize=64)
def _zone(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError, OSError:
        return None


def is_valid_timezone(name: str) -> bool:
    """Ob `name` eine bekannte IANA-Zeitzone ist („Europe/Berlin“, „UTC“)."""
    return bool(name) and _zone(name) is not None


def check_timezone(name: str) -> str:
    """Pydantic-Prüfer: wirft `ValueError` mit deutscher Meldung bei unbekannter Zone."""
    if not is_valid_timezone(name):
        raise ValueError(
            f"ist keine bekannte Zeitzone („{name}“), bitte einen IANA-Namen wie "
            f"„{DEFAULT_TIMEZONE}“ angeben"
        )
    return name


def zone(name: str | None) -> ZoneInfo:
    """Zeitzone zum Namen; ohne oder mit unbekanntem Namen die Standardzone."""
    found = _zone(name) if name else None
    if found is None:
        found = _zone(DEFAULT_TIMEZONE)
        assert found is not None
    return found


def zone_of(settings: Mapping[str, Any] | None) -> ZoneInfo:
    """Zeitzone eines Turniers aus seinen Einstellungen."""
    value = (settings or {}).get(TIMEZONE_SETTING)
    return zone(value if isinstance(value, str) else None)


def local_iso(moment: datetime | None, tz: ZoneInfo) -> str | None:
    """Zeitpunkt als ISO 8601 in Ortszeit mit Versatz („2027-03-06T10:00:00+01:00“)."""
    if moment is None:
        return None
    return moment.astimezone(tz).isoformat()
