"""Notzugang über die Server-Konsole.

    python -m app.modules.auth.cli pairing-code [--name NAME] [--minutes N]
    python -m app.modules.auth.cli list-users
    python -m app.modules.auth.cli reset-pin NAME-ODER-ID [--pin PIN]
    python -m app.modules.auth.cli ensure-admin NAME [--pin PIN]
    python -m app.modules.auth.cli enforcement status|on|off

Im Container: `docker compose exec backend python -m app.modules.auth.cli …`.

Für den Fall, dass der Verein ausgesperrt ist (Admin-Gerät verloren, Browserdaten gelöscht, PIN
vergessen). Wer die Konsole des Servers bedienen kann, darf das; über das Netz ist nichts davon
erreichbar. Die Datenbank kommt aus `DATABASE_URL`, die Regeln (PIN-Länge, Laufzeit der Codes)
aus den `AUTH_…`-Einstellungen. Jeder Befehl schreibt einen Audit-Eintrag („über die
Server-Konsole“), nie mit PIN oder Code. Ohne `--pin` wird eine zufällige PIN erzeugt und genau
einmal angezeigt.

`enforcement off` ist der einzige Weg, die in der App eingeschaltete Berechtigungsprüfung wieder
auszuschalten. Der laufende Server liest den Schalter alle `AUTH_ENFORCEMENT_POLL_SECONDS`
Sekunden neu und übernimmt die Änderung ohne Neustart. Steht `AUTH_ENFORCED=true` in der
Umgebung, gilt die Prüfung trotzdem; dann hilft nur, die Variable zu entfernen und den Server neu
zu starten.

Exit-Codes: 0 in Ordnung, 1 Fehler (z. B. Benutzer unbekannt, PIN zu kurz, Datenbank nicht
erreichbar), 2 falscher Aufruf.
"""

import argparse
import asyncio
import secrets
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import TextIO

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_session_factory
from app.core.events import EventHub
from app.core.localtime import zone
from app.core.security import Actor
from app.modules.auth import enforcement as switch
from app.modules.auth import service
from app.modules.auth.audit import record_audit
from app.modules.auth.schemas import Name, PairingCodeIn
from app.modules.auth.settings import AuthSettings

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
# Länger als einen Tag soll kein Kopplungscode gelten.
MAX_PAIRING_MINUTES = 24 * 60
RANDOM_PIN_LENGTH = 6

_name = TypeAdapter(Name)


class CliError(Exception):
    pass


def _clean_name(value: str) -> str:
    try:
        return _name.validate_python(value)
    except ValidationError as exc:
        raise CliError(f"Der Name muss 1 bis 80 Zeichen lang sein („{value}“).") from exc


def _random_pin(settings: AuthSettings) -> str:
    length = max(RANDOM_PIN_LENGTH, settings.pin_min_length)
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _local(moment: datetime) -> str:
    return moment.astimezone(zone(None)).strftime("%d.%m.%Y %H:%M:%S %Z")


def _base_urls(configured: str) -> list[str]:
    return [url.strip().rstrip("/") for url in configured.split(",") if url.strip()]


def _show_pin(pin: str, out: TextIO) -> None:
    print(f"Neue PIN: {pin}", file=out)
    print("Die PIN wird nur jetzt angezeigt. Bitte notieren und weitergeben.", file=out)


# --- Befehle -----------------------------------------------------------------


async def pairing_code(
    session: AsyncSession,
    settings: Settings,
    *,
    name: str | None,
    minutes: float | None,
    out: TextIO = sys.stdout,
) -> str:
    """Erzeugt einen einmaligen Kopplungscode und gibt ihn mit Adresse aus. Liefert den Code."""
    if minutes is not None and not 0 < minutes <= MAX_PAIRING_MINUTES:
        raise CliError(f"--minutes muss größer als 0 und höchstens {MAX_PAIRING_MINUTES} sein.")
    body = PairingCodeIn(name=_clean_name(name) if name is not None else None)
    created = await service.create_pairing_code(
        session,
        Actor(),
        AuthSettings.from_settings(settings),
        EventHub(),
        body,
        minutes=minutes,
        via=service.CONSOLE_VIA,
    )
    print(f"Kopplungscode: {created.code}", file=out)
    if created.name:
        print(f"Gerätename:    {created.name}", file=out)
    print(f"Gültig bis:    {_local(created.expires_at)} (nur einmal verwendbar)", file=out)
    urls = _base_urls(settings.public_base_url)
    if urls:
        print("Kopplungsadresse(n):", file=out)
        for url in urls:
            print(f"  {url}{created.pair_path}", file=out)
    else:
        print(f"Kopplungspfad: {created.pair_path}", file=out)
        print(
            "PUBLIC_BASE_URL ist nicht gesetzt: bitte die Serveradresse davorsetzen, "
            f"z. B. https://192.168.178.20{created.pair_path}",
            file=out,
        )
    return created.code


async def list_users(session: AsyncSession, *, out: TextIO = sys.stdout) -> None:
    users = await service.console_list_users(session)
    if not users:
        print("Es gibt noch keine Benutzer (Ersteinrichtung offen).", file=out)
        return
    width = max(len(user.name) for user in users)
    role_width = max(len(user.role_name) for user in users)
    for user in users:
        state = "aktiv" if user.active else "inaktiv"
        if user.locked_until is not None:
            state += f", gesperrt bis {_local(user.locked_until)}"
        print(f"{user.name:<{width}}  {user.role_name:<{role_width}}  {state}  {user.id}", file=out)
    if not any(user.is_admin and user.active for user in users):
        print(
            "Achtung: Es gibt keinen aktiven Administrator. Abhilfe: ensure-admin NAME",
            file=out,
        )


async def reset_pin(
    session: AsyncSession,
    settings: Settings,
    *,
    who: str,
    pin: str | None,
    out: TextIO = sys.stdout,
) -> None:
    auth = AuthSettings.from_settings(settings)
    user = await service.find_user(session, who)
    new_pin = pin if pin is not None else _random_pin(auth)
    result = await service.reset_pin(
        session, Actor(), auth, EventHub(), user.id, new_pin, via=service.CONSOLE_VIA
    )
    print(f"PIN für „{result.name}“ gesetzt, eine Sperre ist aufgehoben.", file=out)
    print("Bestehende Anmeldungen dieses Benutzers sind beendet.", file=out)
    if pin is None:
        _show_pin(new_pin, out)
    if not result.active:
        print(
            "Hinweis: Der Benutzer ist inaktiv und kann sich so nicht anmelden "
            "(ensure-admin reaktiviert Administratoren).",
            file=out,
        )


async def ensure_admin(
    session: AsyncSession,
    settings: Settings,
    *,
    name: str,
    pin: str | None,
    out: TextIO = sys.stdout,
) -> None:
    auth = AuthSettings.from_settings(settings)
    clean = _clean_name(name)
    generated: str | None = None
    if pin is None and not await service.user_name_taken(session, clean):
        generated = _random_pin(auth)
    result = await service.console_ensure_admin(
        session, auth, EventHub(), clean, pin if pin is not None else generated
    )
    if result.created:
        print(f"Administrator „{result.user.name}“ angelegt.", file=out)
        if generated is not None:
            _show_pin(generated, out)
    else:
        done = []
        if "role_id" in result.changes:
            done.append("hat jetzt die Rolle Administrator")
        if "active" in result.changes:
            done.append("ist wieder aktiv")
        if "unlocked" in result.changes:
            done.append("ist entsperrt")
        if "pin_reset" in result.changes:
            done.append("hat eine neue PIN")
        summary = ", ".join(done) if done else "war bereits aktiver Administrator"
        print(f"„{result.user.name}“ {summary}.", file=out)
        if pin is None:
            print("PIN unverändert (neue PIN: reset-pin NAME).", file=out)
    print("Ein neues Gerät koppeln: pairing-code --name GERÄTENAME", file=out)


ENV_WINS = (
    "Achtung: AUTH_ENFORCED=true steht in der Umgebung des Servers und gewinnt – die Prüfung "
    "bleibt an. Zum Ausschalten AUTH_ENFORCED entfernen (oder auf false setzen) und den Server "
    "neu starten."
)


async def enforcement(
    session: AsyncSession, settings: Settings, *, action: str, out: TextIO = sys.stdout
) -> None:
    """Berechtigungsprüfung anzeigen (`status`), einschalten (`on`) oder ausschalten (`off`)."""
    env = settings.auth_enforced
    stored = await switch.load(session)
    poll = settings.auth_enforcement_poll_seconds
    if action == "status":
        effective = "an" if env or stored else "aus"
        print(f"Berechtigungsprüfung: {effective}", file=out)
        print(f"  AUTH_ENFORCED (Umgebung):     {'true' if env else 'false'}", file=out)
        print(f"  In der App eingeschaltet:     {'ja' if stored else 'nein'}", file=out)
        if env:
            print(
                "Die Umgebungsvariable gewinnt; ausschalten nur über AUTH_ENFORCED und Neustart.",
                file=out,
            )
        elif stored:
            print("Ausschalten: enforcement off", file=out)
        return

    wanted = action == "on"
    if stored == wanted:
        print(
            f"Der gespeicherte Schalter ist bereits {'an' if wanted else 'aus'}. Nichts geändert.",
            file=out,
        )
    else:
        if wanted and not await switch.full_admin_exists(session):
            raise CliError(
                "Es gibt keinen aktiven Administrator mit PIN – niemand könnte sich anmelden. "
                "Zuerst: ensure-admin NAME"
            )
        await switch.store(session, wanted)
        record_audit(
            session,
            Actor(),
            "auth.enforcement_enabled" if wanted else "auth.enforcement_disabled",
            "setting",
            switch.SETTING_KEY,
            {"via": service.CONSOLE_VIA},
        )
        await session.commit()
        print(
            f"Berechtigungsprüfung {'eingeschaltet' if wanted else 'ausgeschaltet'}. Der laufende "
            f"Server übernimmt das innerhalb von etwa {poll:g} Sekunden (kein Neustart nötig).",
            file=out,
        )
    if env and not wanted:
        print(ENV_WINS, file=out)


# --- Aufruf ------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.modules.auth.cli",
        description=(
            "Notzugang über die Server-Konsole: Geräte koppeln, PINs, Administratoren, "
            "Berechtigungsprüfung."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="BEFEHL")
    code = commands.add_parser("pairing-code", help="einmaligen Kopplungscode erzeugen")
    code.add_argument("--name", help="Vorschlag für den Gerätenamen")
    code.add_argument(
        "--minutes", type=float, help="Gültigkeit in Minuten (Standard: AUTH_PAIRING_CODE_MINUTES)"
    )
    commands.add_parser("list-users", help="Benutzer mit Rolle und Zustand anzeigen")
    reset = commands.add_parser("reset-pin", help="PIN setzen und Sperre aufheben")
    reset.add_argument("who", metavar="NAME-ODER-ID", help="Name oder ID des Benutzers")
    reset.add_argument("--pin", help="neue PIN (ohne Angabe: zufällig, einmal angezeigt)")
    admin = commands.add_parser("ensure-admin", help="Administrator anlegen oder reaktivieren")
    admin.add_argument("name", metavar="NAME", help="Name des Benutzers")
    admin.add_argument("--pin", help="PIN (neuer Benutzer ohne Angabe: zufällig, einmal angezeigt)")
    switch_cmd = commands.add_parser(
        "enforcement", help="Berechtigungsprüfung anzeigen, ein- oder ausschalten"
    )
    switch_cmd.add_argument("action", choices=("status", "on", "off"), metavar="status|on|off")
    return parser


async def run(args: argparse.Namespace, settings: Settings, out: TextIO = sys.stdout) -> None:
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            match args.command:
                case "pairing-code":
                    await pairing_code(
                        session, settings, name=args.name, minutes=args.minutes, out=out
                    )
                case "list-users":
                    await list_users(session, out=out)
                case "reset-pin":
                    await reset_pin(session, settings, who=args.who, pin=args.pin, out=out)
                case "ensure-admin":
                    await ensure_admin(session, settings, name=args.name, pin=args.pin, out=out)
                case "enforcement":
                    await enforcement(session, settings, action=args.action, out=out)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        asyncio.run(run(args, settings or get_settings()))
    except HTTPException as exc:
        print(f"Fehler: {exc.detail}", file=sys.stderr)
        return EXIT_ERROR
    except CliError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except service.MissingSystemRoleError as exc:
        print(f"Fehler: {exc} Bitte den Server einmal starten.", file=sys.stderr)
        return EXIT_ERROR
    except (SQLAlchemyError, OSError) as exc:
        print(f"Fehler: Datenbank nicht erreichbar oder nicht bereit ({exc}).", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
