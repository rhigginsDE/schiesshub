"""Einstiegspunkt: baut die FastAPI-Anwendung und registriert alle Module."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute

from app import __version__
from app.core.config import API_PREFIX, Settings, get_settings
from app.core.db import create_engine, create_session_factory
from app.core.errors import install_error_handlers
from app.core.events import EventHub
from app.core.logging import configure_access_log
from app.modules import MODULES

logger = logging.getLogger("schiesshub")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    try:
        for module in MODULES:
            if module.on_startup is not None:
                await module.on_startup(app)
        yield
    finally:
        for module in reversed(MODULES):
            if module.on_shutdown is not None:
                await module.on_shutdown(app)
        await engine.dispose()


def _operation_id(route: APIRoute) -> str:
    """Kurze, stabile Namen für den aus OpenAPI erzeugten TypeScript-Client."""
    return f"{route.tags[0]}_{route.name}" if route.tags else route.name


DOCS_PATH = f"{API_PREFIX}/docs"
DOCS_BANNER = (
    '<div style="background:#b45309;color:#fff;padding:8px 16px;font:14px sans-serif">'
    "<strong>Nur Entwicklung</strong> (ENVIRONMENT=development): Diese Seite lädt Swagger-UI "
    "aus dem Internet (cdn.jsdelivr.net). Auf dem Turnier-Server ist sie abgeschaltet; "
    "die Beschreibung selbst liegt immer unter <code>openapi.json</code>.</div>"
)


def _add_dev_docs(app: FastAPI) -> None:
    """API-Dokumentation nur in der Entwicklung: Swagger-UI käme sonst von einem CDN, und der
    Server im Schützenhaus läuft ohne Internet (docs/ARCHITEKTUR.md, „Offline zuerst“)."""

    async def docs() -> HTMLResponse:
        page = get_swagger_ui_html(
            openapi_url=app.openapi_url or "",
            title=f"{app.title} API – nur Entwicklung",
            swagger_favicon_url="data:,",
        )
        html = bytes(page.body).decode("utf-8").replace("<body>", f"<body>{DOCS_BANNER}", 1)
        return HTMLResponse(html)

    app.add_api_route(DOCS_PATH, docs, methods=["GET"], include_in_schema=False)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    configure_access_log()

    app = FastAPI(
        title="Schiesshub",
        version=__version__,
        description="Turnier-Erfassung für Schießvereine.",
        openapi_url=f"{API_PREFIX}/openapi.json",
        # Eigene Seite, nur in der Entwicklung (siehe _add_dev_docs).
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    app.state.events = EventHub()
    install_error_handlers(app)
    if settings.is_development:
        _add_dev_docs(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in MODULES:
        app.include_router(module.router, prefix=API_PREFIX)
        logger.debug("Modul registriert: %s", module.name)

    return app


app = create_app()
