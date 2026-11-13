"""Конфигурация сессий базы данных.

Автор: Maxi-online
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session():
    """Отдать асинхронную сессию SQLAlchemy как зависимость.

    :yield: Активная сессия, привязанная к текущему запросу.
    """

    async with SessionLocal() as session:
        yield session
