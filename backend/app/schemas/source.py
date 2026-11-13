"""Схемы источника для API.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SourceBase(BaseModel):
    """Базовая схема источника.

    Атрибуты:
        name: Человекочитаемое имя источника.
        url: Базовый URL источника.
        kind: Тип источника (rss, html, sitemap, api).
        status: Статус источника (active, disabled).
        auto_discovered: Признак автообнаружения.
    """

    name: str | None = None
    url: str
    kind: str
    status: str = "active"
    auto_discovered: bool = False


class SourceCreate(SourceBase):
    """Схема для создания источника на входе API."""

    model_config = ConfigDict(extra="forbid")


class SourceRead(SourceBase):
    """Схема источника для чтения из API.

    Атрибуты:
        id: Внутренний идентификатор записи.
        last_checked_at: Дата последней проверки.
        created_at: Дата создания записи.
    """

    id: int
    last_checked_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True
