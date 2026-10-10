"""Lightweight periodic recovery; does not delay HTTP server startup."""
import asyncio
import logging
from app.services.ingestion_service import cleanup_pending_uploads
from app.services.storage_service import storage_settings

logger = logging.getLogger(__name__)


async def recover_uploads():
    while True:
        await asyncio.sleep(60)
        if storage_settings.file_storage_backend == "supabase":
            try:
                await asyncio.to_thread(cleanup_pending_uploads)
            except Exception:
                logger.warning("Upload recovery unavailable; will retry")
