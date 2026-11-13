"""Модель источника данных.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Source(Base):
    """Сущность источника данных (RSS/HTML/Sitemap/API).

    Атрибуты:
        id: Внутренний идентификатор записи.
        name: Человекочитаемое имя источника.
        url: Базовый URL источника.
        kind: Тип источника (rss, html, sitemap, api).
        status: Текущий статус источника (active, disabled).
        auto_discovered: Признак автообнаружения.
        last_checked_at: Дата последней проверки.
        created_at: Дата создания записи.
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="active")
    auto_discovered: Mapped[bool] = mapped_column(default=False)
    last_checked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
