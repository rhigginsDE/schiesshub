# syntax=docker/dockerfile:1
# Backend-Image für Schiesshub. Build-Kontext ist die Repo-Wurzel:
#   docker build -f deploy/backend.Dockerfile --target prod -t schiesshub-backend .
#
# Targets:
#   dev   – alle Abhängigkeiten inkl. Test- und Lint-Werkzeuge, uv an Bord; Code kommt per Bind-Mount
#   prod  – nur Laufzeit-Abhängigkeiten, Code und Katalog fest im Image

ARG PYTHON_IMAGE=python:3.15.2-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.9
# Hauptversion des PostgreSQL-Clients (pg_dump, pg_restore). Muss zum Server in compose.yaml passen.
ARG PG_MAJOR=19

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS base

ARG PG_MAJOR

# pg_dump/pg_restore für die Sicherung, aus dem offiziellen PGDG-Repository: Debian trixie selbst
# liefert nur PostgreSQL 17, und ein älterer pg_dump verweigert den Abzug eines neueren Servers.
# Der Schlüssel ist per Prüfsumme festgenagelt.
ADD --chmod=644 --checksum=sha256:0144068502a1eddd2a0280ede10ef607d1ec592ce819940991203941564e8e76 \
    https://www.postgresql.org/media/keys/ACCC4CF8.asc /usr/share/keyrings/pgdg.asc
RUN echo "deb [signed-by=/usr/share/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends "postgresql-client-${PG_MAJOR}" \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Die virtuelle Umgebung liegt außerhalb von /app, damit der Bind-Mount sie nicht verdeckt.
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH=/opt/venv/bin:/usr/lib/postgresql/${PG_MAJOR}/bin:$PATH \
    CATALOG_DIR=/catalog

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --home-dir /home/app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data /backup-usb \
    && chown app:app /data /backup-usb

WORKDIR /app

COPY --chmod=755 deploy/backend-entrypoint.sh /usr/local/bin/backend-entrypoint

# ---------------------------------------------------------------------------
FROM base AS dev

COPY --from=uv /uv /uvx /usr/local/bin/

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-install-project \
    && rm -rf /tmp/uv-cache

COPY backend/ ./

USER app
EXPOSE 8000
ENTRYPOINT ["backend-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "/app/app", "--timeout-graceful-shutdown", "2"]

# ---------------------------------------------------------------------------
FROM base AS prod-deps

COPY --from=uv /uv /usr/local/bin/

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# ---------------------------------------------------------------------------
FROM base AS prod

ENV ENVIRONMENT=production

COPY --from=prod-deps /opt/venv /opt/venv
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY catalog/ /catalog/

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]
ENTRYPOINT ["backend-entrypoint"]
# Ein einzelner Worker: Der SSE-Verteiler hält seine Abonnenten im Speicher des Prozesses.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "5"]
