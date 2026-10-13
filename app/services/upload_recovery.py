"""Lightweight periodic recovery; does not delay HTTP server startup."""
import asyncio
import logging
from app.services.ingestion_service import cleanup_pending_uploads

logger = logging.getLogger(__name__)


async def recover_uploads():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(cleanup_pending_uploads)
        except Exception:
            logger.warning("Upload recovery unavailable; will retry")
