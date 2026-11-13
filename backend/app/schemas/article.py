"""Схемы статьи для API.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArticleBase(BaseModel):
    """Базовая схема статьи.

    Атрибуты:
        source_id: Идентификатор источника.
        source: Источник публикации.
        url: Ссылка на статью.
        title: Заголовок статьи.
        published_at: Дата публикации.
        text: Полный текст статьи.
        entities: Извлеченные сущности.
        label: Метка классификации.
        quality_flag: Признак качества данных.
    """

    source_id: int | None = None
    source: str | None = None
    url: str
    title: str | None = None
    published_at: datetime | None = None
    text: str | None = None
    entities: dict | None = None
    label: str | None = None
    quality_flag: bool = True


class ArticleCreate(ArticleBase):
    """Схема для создания статьи на входе API."""

    model_config = ConfigDict(extra="forbid")


class ArticleRead(ArticleBase):
    """Схема статьи для чтения из API.

    Атрибуты:
        id: Внутренний идентификатор записи.
    """

    id: int

    class Config:
        from_attributes = True
