"""Berechtigungen: Muster auswerten, bekannte Berechtigungen sammeln, Startrollen.

Eine Rolle speichert Namen (`club.edit`) oder Muster: `person.*` deckt alle Berechtigungen des
Bereichs `person` ab, `*` alle überhaupt. Ausgewertet wird erst bei der Prüfung; Berechtigungen,
die ein Modul später mitbringt, greifen deshalb ohne Änderung an den Rollen.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Gültige Einträge einer Rolle: `*`, `bereich.*` oder `bereich.aktion` (auch mehrteilig).
PERMISSION_PATTERN = re.compile(r"^(\*|[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*(\.\*)?)$")

ADMIN_ROLE_NAME = "Administrator"

# Startrollen. Werden in einer leeren Datenbank angelegt, danach frei änderbar (außer
# Administrator). Solange niemand die Rechte einer Startrolle von Hand ändert, gleicht der Server
# sie bei jedem Start an diese Zuordnung an (`service.reconcile_roles`).
STARTER_ROLES: dict[str, tuple[str, ...]] = {
    ADMIN_ROLE_NAME: ("*",),
    "Turnierleitung": (
        "tournament.*",
        "entry.*",
        "start.*",
        "result.*",
        "person.*",
        "club.edit",
        "export.*",
        "display.*",
        "backup.read",
    ),
    "Kasse": (
        "entry.*",
        "start.read",
        "start.edit",
        "person.*",
        "club.edit",
        "tournament.read",
    ),
    "Auswertung": (
        "result.read",
        "result.capture",
        "start.read",
        "start.call",
        "entry.read",
        "tournament.read",
    ),
    # Nur Lesen der Anzeige-Sichten.
    "Anzeige": (
        "display.read",
        "start.read",
        "result.read",
        "tournament.read",
    ),
}


@dataclass(frozen=True, slots=True)
class KnownPermission:
    permission: str
    module: str
    module_title: str


def matches(pattern: str, permission: str) -> bool:
    if pattern in {"*", permission}:
        return True
    return pattern.endswith(".*") and permission.startswith(pattern[:-1])


def grants(patterns: Iterable[str], permission: str) -> bool:
    return any(matches(pattern, permission) for pattern in patterns)


def known_permissions() -> list[KnownPermission]:
    """Alle Berechtigungen aus den Manifesten aller Module, je Name einmal (erstes Modul gilt)."""
    # Spät importiert: app.modules importiert dieses Modul.
    from app.modules import MODULES

    seen: dict[str, KnownPermission] = {}
    for module in MODULES:
        for permission in module.permissions:
            seen.setdefault(permission, KnownPermission(permission, module.name, module.title))
    return sorted(seen.values(), key=lambda item: item.permission)


def expand(patterns: Iterable[str], *, is_system: bool = False) -> list[str]:
    """Die bekannten Berechtigungen, die eine Rolle tatsächlich gewährt."""
    pattern_list = ["*"] if is_system else list(patterns)
    return [
        item.permission for item in known_permissions() if grants(pattern_list, item.permission)
    ]


def _area(permission: str) -> str:
    """Bereich einer Berechtigung: der erste Teil (`result` bei `result.capture`)."""
    return permission.split(".", 1)[0]


def obsolete_entries(entries: Iterable[str], known: Iterable[str]) -> list[str]:
    """Einträge einer Rolle, die es nicht (mehr) gibt.

    Das sind genaue Namen (kein Muster) aus einem Bereich, den ein Modul führt, die dieses Modul
    aber nicht kennt, etwa `entry.create`, wenn `starts` nur `entry.read` und `entry.edit`
    bringt. Muster (`entry.*`, `*`) und Namen aus Bereichen ohne Modul (etwa `display.read`,
    bevor das Anzeige-Modul eingebunden ist) bleiben stehen: Sie greifen, sobald ein Modul sie
    mitbringt.
    """
    known_set = set(known)
    areas = {_area(permission) for permission in known_set}
    return [
        entry
        for entry in entries
        if "*" not in entry and entry not in known_set and _area(entry) in areas
    ]
