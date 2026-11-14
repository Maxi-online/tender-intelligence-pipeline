"""FastAPI entry point of the application.

Author: Maxi-online
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from app.api.routes import router
from app.api.seldon_routes import router as seldon_router
from app.api import documents as documents_api
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.init_db import create_all
from app.db.session import SessionLocal
from app.models.source import Source
from app.services.config_loader import load_sources_config
from app.services.pipeline import ingest_sources
from app.tasks.celery_app import celery_app
from sqlalchemy import select

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(seldon_router, prefix=settings.api_prefix)
app.include_router(documents_api.router, prefix=settings.api_prefix)


@app.on_event("startup")
async def bootstrap_sources_on_startup() -> None:
    """Load YAML sources and start a permanent parsing cycle.

    Parser spins in the background without stopping: handles all sources and links from the database,
    Waiting for the interval, processing again. Unprocessed sources/references are captured
    every passage.
    """

    await create_all()

    try:
        items = load_sources_config()
    except FileNotFoundError as e:
        logger.warning('Source confiscation not found (%s), download only from database.', e)
        items = []
    except Exception as e:
        logger.exception('Download error config/sources.yaml: %s', e)
        items = []

    added = 0
    async with SessionLocal() as session:
        for item in items:
            url = item.get("url")
            if not url:
                continue
            exists = await session.execute(select(Source).where(Source.url == url))
            if exists.scalars().first():
                continue
            session.add(
                Source(
                    name=item.get("name"),
                    url=url,
                    kind=item.get("kind", "html"),
                    status=item.get("status", "active"),
                    auto_discovered=item.get("auto_discovered", False),
                )
            )
            added += 1
        await session.commit()

    if items:
        logger.info('Start: downloaded sources from config: %s, added new: %s', len(items), added)

    interval = max(60.0, getattr(settings, "ingest_loop_interval_seconds", 300.0))

    async def ingest_loop() -> None:
        'Endless cycle: parsing of all database sources, pause, repeat.'
        while True:
            try:
                async with SessionLocal() as session:
                    n = await ingest_sources(session)
                logger.info('Parsing: Passage completed, articles processed: %s. Next in %s s.', n, int(interval))
            except asyncio.CancelledError:
                logger.info('Parsing: Cycle stopped.')
                raise
            except Exception as e:
                logger.exception('Parking: error of passage: %s. Repeat with %s s.', e, int(interval))
            await asyncio.sleep(interval)

    asyncio.create_task(ingest_loop())
    logger.info('Parsing: Permanent cycle started (interval %s c).', int(interval))

    try:
        celery_app.send_task("tpis.update_cycle")
        logger.info('The background update cycle is in line.')
    except Exception as exc:  # noqa: BLE001
        logger.warning('Unable to start background cycle: %s', exc)
