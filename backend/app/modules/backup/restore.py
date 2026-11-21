"""Wiederherstellung einer Sicherung auf der Kommandozeile.

    python -m app.modules.backup.restore DATEI --database-url URL --data-dir DIR [--create-database]

DATEI ist eine Sicherung vom Stick oder aus dem Download (`.shb`, verschlüsselt), eine
unverschlüsselte Stick-Kopie (`.tar`) oder ein lokaler Abzug (`.dump`, ohne Schlüssel). Das
Sicherungspasswort kommt aus der Umgebungsvariablen `SCHIESSHUB_BACKUP_PASSPHRASE` oder wird
abgefragt. Ablauf: entschlüsseln, Prüfsumme des Abzugs prüfen, Schlüsselverzeichnis nach
DIR/keys schreiben (vorhandene Schlüssel werden nie überschrieben), Abzug mit pg_restore in die
Ziel-Datenbank einspielen. Die Ziel-Datenbank muss leer sein; die laufende Datenbank wird bewusst
nicht als Standard angenommen.

Eine Mitschrift (`.shbj` oder `.ndjson`) wird entschlüsselt und als NDJSON ausgegeben
(`--output`, sonst Standardausgabe).
"""

import argparse
import asyncio
import getpass
import os
import shutil
import sys
import tempfile
from pathlib import Path

import asyncpg

from app.modules.backup import archive, crypto, fsutil, journal, pgtools

PASSPHRASE_ENV = "SCHIESSHUB_BACKUP_PASSPHRASE"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_WRONG_PASSPHRASE = 2
RESTORE_TIMEOUT_S = 3600.0


class RestoreError(Exception):
    pass


def _passphrase() -> str:
    value = os.environ.get(PASSPHRASE_ENV)
    if value:
        return value
    if not sys.stdin.isatty():
        raise RestoreError(
            f"Kein Sicherungspasswort: {PASSPHRASE_ENV} setzen oder interaktiv starten."
        )
    return getpass.getpass("Sicherungspasswort: ")


def _detect(path: Path) -> str:
    with path.open("rb") as file:
        head = file.read(512)
    if head.startswith(crypto.MAGIC):
        return "encrypted"
    if head.startswith(crypto.JOURNAL_PREFIX) or head.startswith(b'{"at"'):
        return "journal"
    if head.startswith(b"PGDMP"):
        return "dump"
    if len(head) >= 262 and head[257:262] == b"ustar":
        return "archive"
    raise RestoreError("Unbekanntes Dateiformat: keine Schiesshub-Sicherung.")


def unpack(path: Path, work_dir: Path) -> tuple[Path, Path | None]:
    """Entpackt die Sicherung nach `work_dir`; liefert Abzug und (falls enthalten) Schlüssel."""
    kind = _detect(path)
    if kind == "dump":
        print("Lokaler Abzug ohne Schlüsselverzeichnis.", file=sys.stderr)
        expected = fsutil.read_checksum(path)
        if expected is not None and fsutil.sha256_file(path) != expected:
            raise RestoreError("Die Prüfsumme des Abzugs weicht ab.")
        return path, None
    if kind == "journal":
        raise RestoreError("Das ist eine Mitschrift, keine Datenbank-Sicherung.")
    with path.open("rb") as file:
        if kind == "encrypted":
            reader = crypto.DecryptingReader(file, passphrase=_passphrase())
            contents = archive.read_archive(reader, work_dir)
            reader.finish()
        else:
            contents = archive.read_archive(file, work_dir)
    if not contents.database_sha256_ok:
        raise RestoreError("Die Prüfsumme des Datenbank-Abzugs im Archiv weicht ab.")
    assert contents.database_file is not None
    print(
        f"Sicherung vom {contents.manifest.get('created_at')} gelesen, Prüfsumme in Ordnung.",
        file=sys.stderr,
    )
    return contents.database_file, contents.keys_dir


def install_keys(source: Path, data_dir: Path) -> list[str]:
    """Kopiert die Schlüssel nach data_dir/keys. Bricht ab, statt Vorhandenes zu überschreiben."""
    target_root = data_dir / "keys"
    files = [path for path in source.rglob("*") if path.is_file()]
    conflicts = [
        str(path.relative_to(source))
        for path in files
        if (target_root / path.relative_to(source)).exists()
    ]
    if conflicts:
        raise RestoreError(
            "Im Ziel liegen bereits Schlüssel (" + ", ".join(conflicts) + "). Bitte ein leeres "
            "Datenverzeichnis angeben; vorhandene Schlüssel werden nicht überschrieben."
        )
    target_root.mkdir(parents=True, exist_ok=True)
    os.chmod(target_root, 0o700)
    for path in files:
        target = target_root / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fsutil.atomic_write_bytes(target, path.read_bytes(), mode=0o600)
    return [str(path.relative_to(source)) for path in files]


async def _connect(target: pgtools.PgTarget, database: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=target.host,
        port=target.port,
        user=target.user,
        password=target.password,
        database=database,
    )


async def prepare_database(target: pgtools.PgTarget, create: bool) -> None:
    """Stellt sicher, dass die Ziel-Datenbank existiert und leer ist."""
    admin = await _connect(target, "postgres")
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", target.database
        )
        if not exists:
            if not create:
                raise RestoreError(
                    f"Die Ziel-Datenbank „{target.database}“ gibt es nicht "
                    "(mit --create-database anlegen lassen)."
                )
            quoted = '"' + target.database.replace('"', '""') + '"'
            await admin.execute(f"CREATE DATABASE {quoted}")
    finally:
        await admin.close()
    connection = await _connect(target, target.database)
    try:
        tables = await connection.fetchval(
            "SELECT count(*) FROM pg_tables "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
        )
    finally:
        await connection.close()
    if tables:
        raise RestoreError(
            f"Die Ziel-Datenbank „{target.database}“ ist nicht leer ({tables} Tabellen)."
        )


async def restore_backup(
    path: Path, database_url: str, data_dir: Path | None, *, create_database: bool
) -> None:
    target = pgtools.PgTarget.from_url(database_url)
    work_dir = Path(tempfile.mkdtemp(prefix="schiesshub-restore-"))
    try:
        dump, keys = await asyncio.to_thread(unpack, path, work_dir)
        if keys is not None:
            if data_dir is None:
                raise RestoreError("Die Sicherung enthält Schlüssel: bitte --data-dir angeben.")
            installed = await asyncio.to_thread(install_keys, keys, data_dir)
            print(
                f"Schlüssel nach {data_dir / 'keys'} geschrieben: {', '.join(installed)}",
                file=sys.stderr,
            )
        await prepare_database(target, create_database)
        await pgtools.restore(target, dump, RESTORE_TIMEOUT_S)
        print(f"Datenbank „{target.database}“ wiederhergestellt.", file=sys.stderr)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def export_journal(path: Path, output: Path | None) -> int:
    with path.open("rb") as file:
        encrypted = file.read(len(crypto.JOURNAL_PREFIX)) == crypto.JOURNAL_PREFIX
    entries = journal.read_journal_file(path, _passphrase() if encrypted else None)
    data = b"".join(entry.line for entry in entries)
    if output is None:
        sys.stdout.buffer.write(data)
    else:
        fsutil.atomic_write_bytes(output, data, mode=0o600)
    print(f"{len(entries)} Einträge der Mitschrift gelesen.", file=sys.stderr)
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.modules.backup.restore",
        description="Schiesshub-Sicherung prüfen und in eine Ziel-Datenbank zurückspielen.",
    )
    parser.add_argument("file", type=Path, help="Sicherung (.shb, .tar, .dump) oder Mitschrift")
    parser.add_argument("--database-url", help="Ziel-Datenbank, z. B. postgresql://u:p@host/db")
    parser.add_argument("--data-dir", type=Path, help="Datenverzeichnis des Ziels (für keys/)")
    parser.add_argument(
        "--create-database", action="store_true", help="Ziel-Datenbank anlegen, falls sie fehlt"
    )
    parser.add_argument("--output", type=Path, help="Nur Mitschrift: Ausgabedatei")
    args = parser.parse_args(argv)
    try:
        if not args.file.is_file():
            raise RestoreError(f"Die Datei {args.file} gibt es nicht.")
        if _detect(args.file) == "journal":
            export_journal(args.file, args.output)
            return EXIT_OK
        database_url = args.database_url or os.environ.get("RESTORE_DATABASE_URL")
        if not database_url:
            raise RestoreError("Bitte die Ziel-Datenbank mit --database-url angeben.")
        asyncio.run(
            restore_backup(
                args.file, database_url, args.data_dir, create_database=args.create_database
            )
        )
    except crypto.WrongPassphraseError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return EXIT_WRONG_PASSPHRASE
    except (
        RestoreError,
        crypto.BackupCryptoError,
        archive.ArchiveError,
        pgtools.PgToolError,
        OSError,
        asyncpg.PostgresError,
    ) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
