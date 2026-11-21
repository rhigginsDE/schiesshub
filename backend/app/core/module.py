"""Manifest, mit dem sich ein Modul bei der Anwendung anmeldet."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI

StartupHook = Callable[[FastAPI], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    """Beschreibt ein Modul: Name, Router und die Berechtigungen, die es einführt.

    `on_startup` läuft einmal beim Start der Anwendung, nachdem die Datenbank bereitsteht.
    `on_shutdown` läuft beim Beenden, bevor die Datenbankverbindung geschlossen wird.
    """

    name: str
    title: str
    router: APIRouter
    permissions: tuple[str, ...] = ()
    on_startup: StartupHook | None = None
    on_shutdown: StartupHook | None = None
