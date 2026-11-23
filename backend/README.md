# Schiesshub – Backend

Python 3.15, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, PostgreSQL 19. Abhängigkeiten verwaltet
[uv](https://docs.astral.sh/uv/); alles läuft im Container, lokal muss nur Docker installiert sein.

## Starten

In der Repo-Wurzel:

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:8010/api/v1/health
```

| Was | Wo |
|---|---|
| API | <http://localhost:8010/api/v1> |
| API-Dokumentation | <http://localhost:8010/api/v1/docs> (nur mit `ENVIRONMENT=development`) |
| OpenAPI-Beschreibung | <http://localhost:8010/api/v1/openapi.json> |
| Live-Ereignisse (SSE) | <http://localhost:8010/api/v1/events> |
| PostgreSQL | `127.0.0.1:5442`, Zugangsdaten aus `.env` |

Beim Start laufen erst die Migrationen, dann wird der Katalog aus `catalog/` eingelesen. Der Code
ist per Bind-Mount eingebunden; Änderungen unter `backend/app/` starten den Server neu.
Nach Änderungen am Katalog: `docker compose restart backend`.

Logs: `docker compose logs -f backend`.

## Testen und prüfen

```bash
docker compose exec backend pytest
docker compose exec backend ruff check .
docker compose exec backend ruff format .
```

Die API-Tests laufen gegen eine echte PostgreSQL-Datenbank: dieselbe Instanz wie die Entwicklung,
aber eine eigene Datenbank `<POSTGRES_DB>_test`, die bei jedem Lauf neu angelegt wird. Laufen
mehrere Testläufe gleichzeitig, bekommt jeder mit `TEST_DB_SUFFIX` eine eigene Datenbank:
`docker compose exec -e TEST_DB_SUFFIX=_a backend pytest`.

## Migration anlegen

Modelle in `app/modules/<name>/models.py` ändern, dann:

```bash
docker compose exec backend alembic revision --autogenerate -m "kurze beschreibung"
docker compose exec backend alembic upgrade head
```

Die erzeugte Datei unter `migrations/versions/` durchlesen und mit einchecken.
`alembic check` meldet, ob Modelle und Migrationen auseinanderlaufen.

## Abhängigkeiten ändern

`pyproject.toml` anpassen, Lockfile neu erzeugen, Image neu bauen:

```bash
docker compose run --rm --no-deps --entrypoint uv backend lock
docker compose up -d --build
```

## Aufbau

```text
app/
  main.py            baut die Anwendung, registriert alle Module aus app/modules/__init__.py
  core/
    config.py        Einstellungen aus Umgebungsvariablen
    db.py            Engine, Sitzungen, Basisklasse der Tabellen
    errors.py        deutsche Fehlerantworten: 422 (`InputError`), 409 (`ConflictError`, optional mit Feld)
    events.py        Verteiler für Server-Sent Events (im Speicher), bekannte Ereignisnamen
    localtime.py     Ortszeit je Turnier (`settings.timezone`)
    module.py        Modul-Manifest
  modules/
    system/          GET /health, GET /events
    katalog/         Katalog einlesen und bereitstellen
      fileformat.py  Pydantic-Modelle der YAML-Dateien (streng)
      loader.py      Verzeichnis lesen und prüfen
      importer.py    Upsert in die Datenbank
      models.py · schemas.py · service.py · router.py
migrations/          Alembic
tests/
```

**Module.** Ein Modul ist ein Paket mit `router`, `schemas`, `service`, bei Bedarf `models`, und
einem `manifest` (Name, Router, Berechtigungen, optionale Start-Funktion) in seiner `__init__.py`.
Ein neues Modul wird in `app/modules/__init__.py` in die Liste `MODULES` eingetragen.

**Sprache.** Code und Bezeichner sind englisch, ebenso Tabellen und Spalten. Deutsch sind die
Felder der API (wie im Katalog), die Modulnamen und die Kommentare.

**Katalog-Import.** Läuft bei jedem Start. Jeder Verband wird für sich geprüft; unbekannte Felder,
tote Verweise und doppelte Kennziffern sind Fehler. Ein Verband mit Fehlern wird nicht übernommen,
sein alter Stand bleibt stehen, und `GET /health` zeigt die Fehler mit Datei und Pfad
(`status: "eingeschraenkt"`). Einträge, die aus den Dateien verschwinden, werden inaktiv gesetzt,
nicht gelöscht.

**Live-Ereignisse.** `GET /events` sendet `verbunden`, bei Ruhe alle 15 s `heartbeat` und fachliche
Ereignisse wie `katalog.importiert`. Der Verteiler lebt im Speicher eines Prozesses, das Backend
läuft deshalb mit einem Worker. `GET /events/names` listet die bekannten Ereignisnamen: Module
melden ihre Namen beim Laden mit `app.core.events.register_event_names` an, zusätzlich merkt sich
jedes `publish` seinen Namen. `match_names` löst Muster wie `start.*` dagegen auf (so baut die
Anzeige `reload_on`).

**Konflikte.** Fachliche 409 wirft man als `app.core.errors.ConflictError(message, field=None)`.
Mit `field` antwortet der Server wie bei 422 zusätzlich mit `errors`
(`{"detail": "…", "errors": [{"field": "lane", "message": "…"}]}`), ohne nur mit `detail`.

## Berechtigungsprüfung

Ist die Berechtigungsprüfung aus, sind alle Endpunkte ohne Anmeldung erreichbar. Kopplung,
Anmeldung und Verwaltung funktionieren trotzdem. Wirksam ist sie, wenn **eines** von beiden gilt:

- `AUTH_ENFORCED=true` in der Umgebung (fest, nur auf dem Server änderbar, Neustart nötig), oder
- der in der App eingeschaltete Schalter (Tabelle `setting`, Schlüssel `auth_enforcement`).

**Entwicklung:** `AUTH_ENFORCED=false` und den Schalter nicht einschalten. Die Tests setzen
`AUTH_ENFORCED=false` selbst und leeren die Datenbank vor jedem Test, der Schalter bleibt also nicht
hängen.

**Vereinsrechner:** In der App unter System → Server einschalten (`POST /auth/enforcement/enable`,
Recht `system.manage`). Das geht nur, wenn es einen aktiven Benutzer mit PIN und vollen
Verwaltungsrechten gibt (Rolle Administrator oder mindestens `role.manage`, `user.manage`,
`device.manage`, `system.manage`) **und** genau so jemand an dem gekoppelten Gerät angemeldet ist,
von dem die Anfrage kommt. Das gilt auch, solange noch alles offen ist, damit sich niemand
aussperrt. Was fehlt, liefert `GET /auth/enforcement` (für jedes Gerät lesbar):

```json
{"enforced": false, "source": null, "can_enable": false,
 "blockers": [{"code": "device_not_paired", "message_de": "Dieses Gerät ist nicht gekoppelt. …"}]}
```

`source` ist `env`, `setting` oder `null`. Blocker-Codes: `no_admin_with_pin`,
`device_not_paired`, `not_logged_in`, `not_admin`. Fehlt etwas, antwortet `enable` mit 409 und
`code: "enforcement_blocked"`. Nach dem Einschalten gibt es einen Audit-Eintrag
`auth.enforcement_enabled` und das Ereignis `auth.enforcement_changed`
(`{"enforced": true, "source": "setting"}`). Offene Stationen laden damit ihren Status neu und
wechseln zu Kopplung oder Anmeldung.

**Ausschalten** geht absichtlich nicht über die App, sondern nur auf der Konsole:
`python -m app.modules.auth.cli enforcement off` (siehe unten). Der Server hält den Schalter im
Speicher, keine Anfrage fragt dafür die Datenbank. Neu gelesen wird er alle
`AUTH_ENFORCEMENT_POLL_SECONDS` Sekunden (Standard 5), so übernimmt der laufende Server eine
Änderung über die Konsole ohne Neustart und meldet sie ebenfalls als `auth.enforcement_changed`.
Das setzt einen einzelnen Server-Prozess voraus, so läuft das Backend ohnehin (SSE).

## Notzugang über die Server-Konsole

Wenn sich niemand mehr anmelden kann, etwa weil das einzige Admin-Gerät verloren ist, die
Browserdaten gelöscht sind oder die PIN vergessen ist, hilft die Konsole des Servers. Über das
Netz ist das nicht erreichbar:

```bash
docker compose exec backend python -m app.modules.auth.cli pairing-code --name "Leitstand" [--minutes 30]
docker compose exec backend python -m app.modules.auth.cli list-users
docker compose exec backend python -m app.modules.auth.cli reset-pin "Anna Admin" [--pin 1234]
docker compose exec backend python -m app.modules.auth.cli ensure-admin "Anna Admin" [--pin 1234]
docker compose exec backend python -m app.modules.auth.cli enforcement status|on|off
```

| Befehl | Wirkung |
|---|---|
| `pairing-code` | einmaliger Kopplungscode wie über die API; Laufzeit `AUTH_PAIRING_CODE_MINUTES`, mit `--minutes` bis 1440. Ausgabe: Code, Ablaufzeit, Kopplungsadresse(n) aus `PUBLIC_BASE_URL` (ohne diese Einstellung nur der Pfad, die Serveradresse muss man dann selbst davorsetzen) |
| `list-users` | Personen mit Rolle, aktiv/inaktiv, Sperre und ID (keine PIN-Hashes); warnt, wenn kein aktiver Administrator mehr da ist |
| `reset-pin` | setzt die PIN einer Person (Name oder ID), hebt eine Sperre auf und beendet ihre Anmeldungen |
| `ensure-admin` | legt einen Administrator an oder gibt einer vorhandenen Person die Systemrolle, aktiviert und entsperrt sie; die PIN ändert sich bei Vorhandenen nur mit `--pin` |
| `enforcement` | `status` zeigt, ob die Berechtigungsprüfung wirkt und woher (`AUTH_ENFORCED` oder in der App eingeschaltet). `off` schaltet den in der App gesetzten Schalter aus, das ist der einzige Weg dafür; `on` schaltet ihn ein (nur, wenn es einen aktiven Administrator gibt). Der laufende Server übernimmt das innerhalb von `AUTH_ENFORCEMENT_POLL_SECONDS`. Steht `AUTH_ENFORCED=true` in der Umgebung, gewinnt die Variable; der Befehl sagt das, dann hilft nur, sie zu entfernen und den Server neu zu starten |

Ohne `--pin` wird eine zufällige PIN (mindestens 6 Ziffern) erzeugt und nur einmal angezeigt.
Die Mindestlänge `AUTH_PIN_MIN_LENGTH` gilt auch hier. Jeder Befehl schreibt einen Audit-Eintrag
ohne Person und Gerät, mit `details.via = "über die Server-Konsole"`, nie mit PIN oder Code.
Ereignisse (SSE) erreichen offene Browser nicht, weil der Befehl in einem eigenen Prozess läuft;
die Oberfläche zeigt die Änderung nach dem nächsten Laden. Ausnahme ist `enforcement`: Das
Ereignis meldet der Server selbst, sobald er den Schalter neu gelesen hat. Exit-Codes: `0` in Ordnung, `1` Fehler
(Meldung auf stderr), `2` falscher Aufruf.

## Sicherung und Wiederherstellung

Das Modul `backup` macht regelmäßig Datenbank-Abzüge (Standard: alle 5 Minuten) nach
`DATA_DIR/backups/snapshots`. Jedes Ergebnis-Ereignis kommt sofort in die Mitschrift
(`DATA_DIR/backups/journal`). Beides geht verschlüsselt auf den Stick unter `BACKUP_USB_DIR`
(erkannt an `BACKUP_USB_MARKER`). Eine Sicherung auf dem Stick (`.shb`) enthält den Abzug und das
ganze Schlüsselverzeichnis `DATA_DIR/keys`, darunter den Namensschlüssel `field-keys.json`.

Rechte: `backup.read` (ansehen), `backup.run` („Jetzt sichern“, Stick erneut prüfen; hat die
Startrolle Turnierleitung), `backup.manage` (einrichten: Passwort, Ziel, Schalter; schließt
`backup.run` ein), `backup.restore` (wiederherstellen; nur Administrator, nie über eine
Standardrolle eines Geräts).

**Wiederherstellen in der App** (nur angemeldeter Administrator), Ablauf und Folgen in
[docs/WIEDERHERSTELLUNG.md](../docs/WIEDERHERSTELLUNG.md):

| Endpunkt | Zweck |
|---|---|
| `GET /backup/restore/sources` | Sicherungen auf Stick und Server, neueste zuerst |
| `POST /backup/restore/preview` | `{source_id, passphrase}` → Prüfung und Vorschau (Turniere, Vergleich mit dem jetzigen Stand, Schlüssel, Zugang); ändert nichts |
| `POST /backup/restore/execute` | `{source_id, passphrase, confirm: source_id, apply_journal, accept_lockout}` → 202, Hintergrundauftrag |
| `GET /backup/restore/status` | Schritt, Fortschritt, Ergebnis oder Fehler |
| `GET /backup/maintenance` | Wartungszustand, für jedes gekoppelte Gerät |

Die Ausführung sichert zuerst den jetzigen Stand, hält Eingaben an (503 mit
`code: maintenance`, Ereignis `backup.maintenance`), spielt in eine neue Datenbank ein,
aktualisiert sie bei Bedarf (`alembic upgrade heads`), trägt die Mitschrift nach, prüft und tauscht
dann per `ALTER DATABASE … RENAME`. Die alte Datenbank bleibt als `<name>_pre_restore_<Zeit>`.
Dafür braucht der Datenbank-Benutzer `CREATEDB` und muss Eigentümer der Datenbank sein (in der
Entwicklung ist `POSTGRES_USER` Superuser). Fortschritt meldet zusätzlich das Ereignis
`backup.restore` (nur Zustand und Schritt).

**Notweg über die Konsole**, immer in eine neue, leere Datenbank:

```bash
docker compose exec -e SCHIESSHUB_BACKUP_PASSPHRASE='…' backend \
  python -m app.modules.backup.restore /backup-usb/snapshots/snapshot-<Zeit>Z.shb \
    --database-name schiesshub_neu --create-database --data-dir /data \
    --apply-journal /backup-usb/journal
```

`--apply-journal` trägt danach die Ergebnis-Ereignisse aus der Mitschrift nach, die im Abzug
fehlen. Status und Wertung werden nachgezogen, nichts wird doppelt eingetragen. Ereignisse zu
Starts, die erst nach der Sicherung gebucht wurden, werden übersprungen und mit Startnummer
aufgelistet. Ablauf, Prüfung danach und was von Hand nachzutragen ist:
[docs/WIEDERHERSTELLUNG.md](../docs/WIEDERHERSTELLUNG.md). `--help` nennt alle Schalter.
Exit-Codes: `0` in Ordnung, `1` Fehler, `2` Sicherungspasswort falsch, `3` wiederhergestellt,
aber nicht alles aus der Mitschrift nachgetragen.

`GET /backup/warning` liefert jedem gekoppelten Gerät nur die aktuelle Warnung (ohne Pfade,
Dateinamen oder Größen) und die Schalter `warn_all_stations`/`warn_on_display`. Den vollen Status
liefert `GET /backup/status` (Recht `backup.read`).

## Einstellungen

| Variable | Bedeutung | Standard |
|---|---|---|
| `ENVIRONMENT` | `development` schaltet die API-Dokumentation unter `/api/v1/docs` ein (Swagger-UI lädt aus dem Internet); sonst gibt es nur `openapi.json` | `development` |
| `DATABASE_URL` | `postgresql+asyncpg://…` | – (Pflicht) |
| `CATALOG_DIR` | Verzeichnis des Katalogs | `/catalog` |
| `CORS_ORIGINS` | erlaubte Browser-Herkünfte, mit Komma getrennt | `http://localhost:5180` |
| `SSE_HEARTBEAT_SECONDS` | Abstand der Heartbeats | `15` |
| `LOG_LEVEL` | Protokollstufe | `INFO` |
| `DATA_DIR` | beständige Daten außerhalb der Datenbank: Schlüssel (`keys/`), lokale Sicherungen (`backups/`) | `/data` |
| `BACKUP_USB_DIR` | Einhängepunkt des Sicherungs-Sticks | `/backup-usb` |
| `BACKUP_USB_MARKER` | Marker-Datei, an der der Stick erkannt wird | `.schiesshub-backup` |
| `AUTH_ENFORCED` | `true` schaltet die Berechtigungsprüfung fest ein. Bei `false` gilt sie erst, wenn sie in der App eingeschaltet wurde (siehe „Berechtigungsprüfung“) | `false` |
| `AUTH_ENFORCEMENT_POLL_SECONDS` | so oft liest der Server den in der App gesetzten Schalter neu (Änderungen über die Konsole) | `5` |
| `AUTH_PAIRING_CODE_MINUTES` | Gültigkeit eines Kopplungscodes in Minuten | `10` |
| `AUTH_PIN_MIN_LENGTH` | Mindestlänge der PIN (nur Ziffern, 4 bis 12) | `4` |
| `AUTH_MAX_FAILED_LOGINS` | Fehlversuche in Folge bis zur Sperre | `5` |
| `AUTH_LOCKOUT_MINUTES` | Dauer der Sperre in Minuten | `5` |
| `AUTH_SESSION_IDLE_HOURS` | Sitzung endet nach so vielen Stunden ohne Anfrage | `12` |
| `AUTH_COOKIE_SECURE` | `auto` (Secure nur über HTTPS), `always` oder `never` | `auto` |
| `RUN_MIGRATIONS` | `0` schaltet die Migrationen beim Start ab (Container-Einstieg) | `1` |
| `TEST_DB_SUFFIX` | nur Tests: Zusatz am Namen der Testdatenbank, für parallele Läufe | – |

## Produktions-Image

```bash
docker build -f deploy/backend.Dockerfile --target prod -t schiesshub-backend .
```

Enthält nur die Laufzeit-Abhängigkeiten, den Code und den Katalog; läuft als Benutzer `app`.
