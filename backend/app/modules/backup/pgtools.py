"""Aufruf von pg_dump und pg_restore.

Das Datenbankpasswort steht nie in den Prozessargumenten und nie in den Protokollen: Es kommt
über eine temporäre Passwortdatei (`PGPASSFILE`, Rechte 0600), die nach dem Aufruf gelöscht wird.
"""

import asyncio
import contextlib
import logging
import os
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import make_url

logger = logging.getLogger("schiesshub.backup")


class PgToolError(Exception):
    """pg_dump oder pg_restore ist gescheitert. Die Meldung ist für Anwender gedacht."""


@dataclass(frozen=True, slots=True)
class PgTarget:
    host: str
    port: int
    user: str
    database: str
    password: str | None = field(default=None, repr=False)

    @classmethod
    def from_url(cls, url: str) -> PgTarget:
        parsed = make_url(url)
        if parsed.database is None or parsed.username is None:
            raise PgToolError("Die Datenbank-Adresse nennt keine Datenbank oder keinen Benutzer.")
        return cls(
            host=parsed.host or "localhost",
            port=parsed.port or 5432,
            user=parsed.username,
            database=parsed.database,
            password=parsed.password,
        )

    def with_database(self, database: str) -> PgTarget:
        return PgTarget(self.host, self.port, self.user, database, self.password)

    def connection_args(self) -> list[str]:
        return [
            "--no-password",
            f"--host={self.host}",
            f"--port={self.port}",
            f"--username={self.user}",
        ]


def _escape_pgpass(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def base_environment() -> dict[str, str]:
    """Umgebung für Kindprozesse, ohne ein etwa gesetztes PGPASSWORD."""
    return {key: value for key, value in os.environ.items() if key != "PGPASSWORD"}


@contextlib.contextmanager
def pg_environment(target: PgTarget) -> Iterator[dict[str, str]]:
    """Umgebung für einen Kindprozess, mit dem Passwort in einer kurzlebigen Datei."""
    env = base_environment()
    if target.password is None:
        yield env
        return
    directory = Path(tempfile.mkdtemp(prefix="schiesshub-pg-"))
    try:
        passfile = directory / "pgpass"
        fd = os.open(passfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(f"*:*:*:{_escape_pgpass(target.user)}:{_escape_pgpass(target.password)}\n")
        env["PGPASSFILE"] = str(passfile)
        yield env
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise PgToolError(
            f"Das Programm {name} ist auf dem Server nicht installiert "
            "(PostgreSQL-Client in passender Version)."
        )
    return path


async def run_tool(args: list[str], env: dict[str, str], limit_s: float) -> bytes:
    """Startet ein Werkzeug, wartet höchstens `limit_s` Sekunden und liefert stdout."""
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), limit_s)
    except BaseException:
        # Zeitüberschreitung oder Abbruch: den Prozess nicht verwaist weiterlaufen lassen.
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await asyncio.shield(process.wait())
        raise
    if process.returncode != 0:
        message = stderr.decode("utf-8", "replace").strip()
        logger.warning("%s endete mit Code %s: %s", Path(args[0]).name, process.returncode, message)
        last_line = message.splitlines()[-1] if message else "ohne Meldung"
        raise PgToolError(f"{Path(args[0]).name} ist fehlgeschlagen: {last_line}")
    return stdout


async def tool_version(name: str) -> str:
    output = await run_tool([require_tool(name), "--version"], base_environment(), limit_s=30)
    return output.decode().strip()


async def dump(target: PgTarget, out_file: Path, limit_s: float) -> None:
    """Vollständiger Abzug im Custom-Format nach `out_file`."""
    args = [
        require_tool("pg_dump"),
        *target.connection_args(),
        f"--dbname={target.database}",
        "--format=custom",
        f"--file={out_file}",
    ]
    with pg_environment(target) as env:
        try:
            await run_tool(args, env, limit_s)
        except TimeoutError:
            raise PgToolError(
                f"pg_dump hat nicht innerhalb von {limit_s:.0f} s geantwortet."
            ) from None


async def list_contents(dump_file: Path, limit_s: float = 120) -> list[str]:
    """Inhaltsverzeichnis eines Abzugs (`pg_restore --list`), ohne Kommentarzeilen."""
    output = await run_tool(
        [require_tool("pg_restore"), "--list", str(dump_file)], base_environment(), limit_s
    )
    lines = output.decode("utf-8", "replace").splitlines()
    return [line for line in lines if line.strip() and not line.startswith(";")]


async def restore(target: PgTarget, dump_file: Path, limit_s: float) -> None:
    """Spielt einen Abzug in eine leere Datenbank ein, alles in einer Transaktion."""
    args = [
        require_tool("pg_restore"),
        *target.connection_args(),
        f"--dbname={target.database}",
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-privileges",
        str(dump_file),
    ]
    with pg_environment(target) as env:
        try:
            await run_tool(args, env, limit_s)
        except TimeoutError:
            raise PgToolError(
                f"pg_restore hat nicht innerhalb von {limit_s:.0f} s geantwortet."
            ) from None
