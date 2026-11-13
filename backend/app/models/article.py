"""Модель статьи/новости.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Article(Base):
    """Сущность статьи из внешнего источника.

    Атрибуты:
        id: Внутренний идентификатор записи.
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

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))
    source: Mapped[str | None] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    published_at: Mapped[datetime | None]
    text: Mapped[str | None] = mapped_column(Text)
    entities: Mapped[dict | None] = mapped_column(JSON)
    label: Mapped[str | None] = mapped_column(String(64))
    quality_flag: Mapped[bool] = mapped_column(Boolean, default=True)
