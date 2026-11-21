"""Protokoll-Einstellungen des Servers."""

import logging


class DropQueryString(logging.Filter):
    """Entfernt die Abfrage-Parameter aus dem Zugriffsprotokoll.

    Suchanfragen wie `/persons?q=…` enthalten Namen. Die gehören nicht in Logdateien.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn.access: (client, method, full_path, http_version, status)
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path = args[2].split("?", 1)[0]
            record.args = (args[0], args[1], path, args[3], args[4])
        return True


def configure_access_log() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(existing, DropQueryString) for existing in access.filters):
        access.addFilter(DropQueryString())
