"""Точка входа FastAPI приложения.

Автор: Maxi-online
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
    """Загрузить источники из YAML и запустить постоянный цикл парсинга.

    Парсер крутится в фоне без остановки: обрабатывает все источники и ссылки из БД,
    ждёт интервал, снова обрабатывает. Необработанные источники/ссылки подхватываются
    при каждом проходе.
    """

    await create_all()

    try:
        items = load_sources_config()
    except FileNotFoundError as e:
        logger.warning("Конфиг источников не найден (%s), загружаем только из БД.", e)
        items = []
    except Exception as e:
        logger.exception("Ошибка загрузки config/sources.yaml: %s", e)
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
        logger.info("Старт: загружено источников из config: %s, добавлено новых: %s", len(items), added)

    interval = max(60.0, getattr(settings, "ingest_loop_interval_seconds", 300.0))

    async def ingest_loop() -> None:
        """Бесконечный цикл: парсинг всех источников из БД, пауза, повтор."""
        while True:
            try:
                async with SessionLocal() as session:
                    n = await ingest_sources(session)
                logger.info("Парсинг: проход завершён, обработано статей: %s. Следующий через %s с.", n, int(interval))
            except asyncio.CancelledError:
                logger.info("Парсинг: цикл остановлен.")
                raise
            except Exception as e:
                logger.exception("Парсинг: ошибка прохода: %s. Повтор через %s с.", e, int(interval))
            await asyncio.sleep(interval)

    asyncio.create_task(ingest_loop())
    logger.info("Парсинг: постоянный цикл запущен (интервал %s с).", int(interval))

    try:
        celery_app.send_task("tpis.update_cycle")
        logger.info("Фоновый цикл обновления поставлен в очередь.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось запустить фоновый цикл: %s", exc)
