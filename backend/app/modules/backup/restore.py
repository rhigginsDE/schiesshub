"""Wiederherstellung einer Sicherung auf der Kommandozeile.

    python -m app.modules.backup.restore DATEI (--database-url URL | --database-name NAME)
        --data-dir DIR [--create-database] [--apply-journal MITSCHRIFT ...]

DATEI ist eine Sicherung vom Stick oder aus dem Download (`.shb`, verschlüsselt), eine
unverschlüsselte Stick-Kopie (`.tar`) oder ein lokaler Abzug (`.dump`, ohne Schlüssel). Das
Sicherungspasswort kommt aus der Umgebungsvariablen `SCHIESSHUB_BACKUP_PASSPHRASE` oder wird
abgefragt. Ablauf: entschlüsseln, Prüfsumme des Abzugs prüfen, Schlüsselverzeichnis nach
DIR/keys schreiben (vorhandene, abweichende Schlüssel werden nie überschrieben), Abzug mit
pg_restore in die Ziel-Datenbank einspielen, danach die Mitschrift nachtragen
(`journal_apply`). Die Ziel-Datenbank muss leer sein; die laufende Datenbank wird bewusst nicht
als Standard angenommen.

Ohne DATEI, nur mit `--apply-journal`, wird die Mitschrift in eine schon wiederhergestellte
Datenbank nachgetragen (beliebig oft wiederholbar). Eine Mitschrift als DATEI wird nur
entschlüsselt und als NDJSON ausgegeben (`--output`, sonst Standardausgabe).
"""

import argparse
import asyncio
import functools
import getpass
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import asyncpg
from sqlalchemy import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import create_engine, create_session_factory
from app.modules.backup import archive, crypto, fsutil, journal, journal_apply, pgtools

PASSPHRASE_ENV = "SCHIESSHUB_BACKUP_PASSPHRASE"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_WRONG_PASSPHRASE = 2
# Wiederhergestellt, aber aus der Mitschrift ließ sich nicht alles nachtragen (siehe Ausgabe).
EXIT_INCOMPLETE = 3
RESTORE_TIMEOUT_S = 3600.0

HELP_EPILOG = f"""\
Sicherungspasswort:
  aus der Umgebungsvariablen {PASSPHRASE_ENV}, sonst wird es abgefragt (nur
  im Terminal). Ohne Passwort lassen sich .shb und .shbj nicht lesen.

Ablauf:
  1. Sicherung entschlüsseln (.shb) und die Prüfsumme des Datenbank-Abzugs prüfen
  2. Ziel-Datenbank prüfen (muss leer sein, mit --create-database wird sie angelegt)
  3. Schlüsselverzeichnis aus der Sicherung nach DATA_DIR/keys schreiben
     (Namensschlüssel field-keys.json und Sicherungsschlüssel backup-key.json);
     gleiche bleiben stehen, bei abweichenden bricht der Befehl schon vor Schritt 2 ab
  4. Abzug mit pg_restore einspielen (eine Transaktion)
  5. mit --apply-journal: Ergebnis-Ereignisse aus der Mitschrift nachtragen, die nach
     dem Abzug entstanden sind; Starts, die in der Sicherung fehlen, werden
     übersprungen und aufgelistet

Beispiele (im Backend-Container):
  {PASSPHRASE_ENV}=… python -m app.modules.backup.restore \\
      /backup-usb/snapshots/snapshot-….shb --database-name schiesshub_neu \\
      --create-database --data-dir /data --apply-journal /backup-usb/journal
  python -m app.modules.backup.restore --database-name schiesshub_neu \\
      --apply-journal /backup-usb/journal

Exit-Codes: 0 in Ordnung, 1 Fehler, 2 Sicherungspasswort falsch,
  3 wiederhergestellt, aber nicht alles aus der Mitschrift nachgetragen.
"""


class RestoreError(Exception):
    pass


@functools.cache
def _passphrase() -> str:
    """Einmal je Aufruf: Sicherung und Mitschrift fragen nicht zweimal."""
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


def keys_to_install(source: Path, data_dir: Path) -> list[Path]:
    """Schlüsseldateien, die im Ziel fehlen; bricht bei abweichenden vorhandenen ab."""
    target_root = data_dir / "keys"
    conflicts = []
    new = []
    for path in (path for path in source.rglob("*") if path.is_file()):
        target = target_root / path.relative_to(source)
        if not target.exists():
            new.append(path)
        elif target.read_bytes() != path.read_bytes():
            conflicts.append(str(path.relative_to(source)))
    if conflicts:
        raise RestoreError(
            "Im Ziel liegen bereits andere Schlüssel (" + ", ".join(conflicts) + "). Bitte ein "
            "leeres Datenverzeichnis angeben; vorhandene Schlüssel werden nicht überschrieben."
        )
    return new


def install_keys(source: Path, data_dir: Path) -> list[str]:
    """Kopiert die Schlüssel nach data_dir/keys und liefert die neu geschriebenen.

    Liegt eine Datei schon mit gleichem Inhalt dort (Wiederherstellung auf demselben Server),
    bleibt sie stehen. Weicht sie ab, bricht die Wiederherstellung ab, ohne etwas zu schreiben.
    """
    target_root = data_dir / "keys"
    new = keys_to_install(source, data_dir)
    target_root.mkdir(parents=True, exist_ok=True)
    os.chmod(target_root, 0o700)
    for path in new:
        target = target_root / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fsutil.atomic_write_bytes(target, path.read_bytes(), mode=0o600)
    return [str(path.relative_to(source)) for path in new]


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
            # Erst prüfen, dann die Datenbank anfassen: Ein Schlüsselkonflikt ändert nichts.
            await asyncio.to_thread(keys_to_install, keys, data_dir)
        await prepare_database(target, create_database)
        if keys is not None:
            assert data_dir is not None
            installed = await asyncio.to_thread(install_keys, keys, data_dir)
            print(
                f"Schlüssel nach {data_dir / 'keys'}: "
                + (", ".join(installed) + " geschrieben" if installed else "schon vorhanden"),
                file=sys.stderr,
            )
        await pgtools.restore(target, dump, RESTORE_TIMEOUT_S)
        print(f"Datenbank „{target.database}“ wiederhergestellt.", file=sys.stderr)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _is_encrypted_journal(path: Path) -> bool:
    with path.open("rb") as file:
        return file.read(len(crypto.JOURNAL_PREFIX)) == crypto.JOURNAL_PREFIX


def read_journals(paths: list[Path]) -> list[dict[str, Any]]:
    """Liest alle Mitschriften (Dateien oder Verzeichnisse) und liefert die Ergebnis-Ereignisse."""
    files = [file for path in paths for file in journal_apply.journal_files(path)]
    if not files:
        raise RestoreError(
            "Keine Mitschrift gefunden (" + ", ".join(str(path) for path in paths) + ")."
        )
    entries: list[journal.JournalEntry] = []
    for file in files:
        if not file.is_file():
            raise RestoreError(f"Die Mitschrift {file} gibt es nicht.")
        if _detect(file) != "journal":
            raise RestoreError(f"{file} ist keine Mitschrift.")
        read = journal_apply.load_journal(
            file, _passphrase() if _is_encrypted_journal(file) else None
        )
        print(f"Mitschrift {file.name}: {len(read)} Einträge gelesen.", file=sys.stderr)
        entries.extend(read)
    other = journal_apply.other_kinds(entries)
    if other:
        print(
            f"{other} Einträge sind keine Ergebnis-Ereignisse und bleiben außen vor.",
            file=sys.stderr,
        )
    return journal_apply.result_records(entries)


async def apply_journal(database_url: str, records: list[dict[str, Any]]) -> bool:
    """Trägt die Ereignisse in die Ziel-Datenbank nach; True, wenn alles nachgetragen ist."""
    url = make_url(database_url).set(drivername="postgresql+asyncpg")
    engine = create_engine(url.render_as_string(hide_password=False))
    try:
        report = await journal_apply.apply_records(create_session_factory(engine), records)
    finally:
        await engine.dispose()
    for line in report.summary():
        print(line, file=sys.stderr)
    return report.complete


def _database_url(args: argparse.Namespace) -> str:
    if args.database_url and args.database_name:
        raise RestoreError("Bitte entweder --database-url oder --database-name angeben.")
    if args.database_name:
        running = os.environ.get("DATABASE_URL")
        if not running:
            raise RestoreError(
                "--database-name braucht DATABASE_URL (Zugangsdaten des Servers); sonst "
                "--database-url angeben."
            )
        return (
            make_url(running).set(database=args.database_name).render_as_string(hide_password=False)
        )
    url = args.database_url or os.environ.get("RESTORE_DATABASE_URL")
    if not url:
        raise RestoreError(
            "Bitte die Ziel-Datenbank mit --database-url oder --database-name angeben."
        )
    return url


def export_journal(path: Path, output: Path | None) -> int:
    encrypted = _is_encrypted_journal(path)
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
        description=(
            "Schiesshub-Sicherung prüfen und in eine leere Ziel-Datenbank zurückspielen; danach "
            "auf Wunsch die Mitschrift (Ergebnisse seit der Sicherung) nachtragen."
        ),
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "file",
        type=Path,
        nargs="?",
        help="Sicherung (.shb, .tar, .dump) oder eine Mitschrift (.shbj, .ndjson) zum Ausgeben; "
        "weglassen, um nur --apply-journal in eine vorhandene Datenbank auszuführen",
    )
    parser.add_argument(
        "--database-url",
        help="Ziel-Datenbank, z. B. postgresql://u:p@host/db (oder RESTORE_DATABASE_URL)",
    )
    parser.add_argument(
        "--database-name",
        help="Ziel-Datenbank mit den Zugangsdaten aus DATABASE_URL, nur anderer Name "
        "(im Backend-Container bequemer als --database-url)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Datenverzeichnis des Ziel-Servers (DATA_DIR, im Container /data) für keys/",
    )
    parser.add_argument(
        "--create-database", action="store_true", help="Ziel-Datenbank anlegen, falls sie fehlt"
    )
    parser.add_argument(
        "--apply-journal",
        type=Path,
        action="append",
        metavar="MITSCHRIFT",
        help="Mitschrift-Datei oder -Verzeichnis (z. B. /backup-usb/journal); mehrfach möglich. "
        "Trägt Ergebnis-Ereignisse nach, die in der Datenbank fehlen (wiederholbar)",
    )
    parser.add_argument("--output", type=Path, help="Nur Mitschrift ausgeben: Ausgabedatei")
    args = parser.parse_args(argv)
    _passphrase.cache_clear()
    try:
        if args.file is None:
            if not args.apply_journal:
                parser.error("Bitte eine Sicherung angeben oder --apply-journal verwenden.")
            records = read_journals(args.apply_journal)
            complete = asyncio.run(apply_journal(_database_url(args), records))
            return EXIT_OK if complete else EXIT_INCOMPLETE
        if not args.file.is_file():
            raise RestoreError(f"Die Datei {args.file} gibt es nicht.")
        if _detect(args.file) == "journal":
            if args.apply_journal:
                raise RestoreError(
                    "Eine Mitschrift zum Nachtragen bitte mit --apply-journal angeben, ohne "
                    "Sicherungsdatei."
                )
            export_journal(args.file, args.output)
            return EXIT_OK
        database_url = _database_url(args)
        # Mitschriften vor dem Einspielen lesen: Ein falsches Passwort fällt auf, bevor die
        # Datenbank angelegt wird.
        records = read_journals(args.apply_journal) if args.apply_journal else None
        asyncio.run(
            restore_backup(
                args.file, database_url, args.data_dir, create_database=args.create_database
            )
        )
        if records is not None:
            complete = asyncio.run(apply_journal(database_url, records))
            return EXIT_OK if complete else EXIT_INCOMPLETE
    except crypto.WrongPassphraseError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return EXIT_WRONG_PASSPHRASE
    except (
        RestoreError,
        journal_apply.JournalFormatError,
        crypto.BackupCryptoError,
        archive.ArchiveError,
        pgtools.PgToolError,
        OSError,
        asyncpg.PostgresError,
        SQLAlchemyError,
    ) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
