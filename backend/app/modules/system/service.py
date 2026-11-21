"""Status des Servers."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.modules.katalog import service as katalog_service
from app.modules.system.schemas import HealthOut

logger = logging.getLogger("schiesshub.system")


async def get_health(session: AsyncSession) -> HealthOut:
    try:
        await session.execute(text("SELECT 1"))
        katalog = await katalog_service.get_status(session)
    except Exception:
        logger.exception("Health: Datenbank nicht erreichbar.")
        return HealthOut(status="fehler", version=__version__, db="fehler", katalog=None)
    return HealthOut(
        status="eingeschraenkt" if katalog.fehler else "ok",
        version=__version__,
        db="ok",
        katalog=katalog,
    )
