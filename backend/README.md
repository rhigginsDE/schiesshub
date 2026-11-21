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
| API-Dokumentation | <http://localhost:8010/api/v1/docs> |
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
aber eine eigene Datenbank `<POSTGRES_DB>_test`, die bei jedem Lauf neu angelegt wird.

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
    events.py        Verteiler für Server-Sent Events (im Speicher)
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
läuft deshalb mit einem Worker.

## Einstellungen

| Variable | Bedeutung | Standard |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…` | – (Pflicht) |
| `CATALOG_DIR` | Verzeichnis des Katalogs | `/catalog` |
| `CORS_ORIGINS` | erlaubte Browser-Herkünfte, mit Komma getrennt | `http://localhost:5180` |
| `SSE_HEARTBEAT_SECONDS` | Abstand der Heartbeats | `15` |
| `LOG_LEVEL` | Protokollstufe | `INFO` |
| `RUN_MIGRATIONS` | `0` schaltet die Migrationen beim Start ab | `1` |

## Produktions-Image

```bash
docker build -f deploy/backend.Dockerfile --target prod -t schiesshub-backend .
```

Enthält nur die Laufzeit-Abhängigkeiten, den Code und den Katalog; läuft als Benutzer `app`.
