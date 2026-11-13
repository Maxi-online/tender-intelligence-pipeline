"""Модели наборов ключевых слов для поиска.

Автор: адаптация под TPIS.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SearchKeywordSet(Base):
    """Набор ключевых слов/промптов для поисковых сценариев.

    Атрибуты:
        id: Внутренний идентификатор набора.
        name: Человеко-читаемое название.
        description: Описание назначения набора.
        created_by: Идентификатор автора (произвольная строка).
        created_at: Дата/время создания.
        updated_at: Дата/время последнего обновления.
    """

    __tablename__ = "search_keyword_sets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    keywords: Mapped[list["SearchKeyword"]] = relationship(
        "SearchKeyword",
        back_populates="keyword_set",
        cascade="all, delete-orphan",
    )


class SearchKeyword(Base):
    """Конкретное ключевое слово/промпт в составе набора.

    Атрибуты:
        id: Внутренний идентификатор.
        set_id: Идентификатор набора.
        text: Текст ключевого слова или промпта.
        weight: Вес/приоритет (по умолчанию 1.0).
    """

    __tablename__ = "search_keywords"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(
        ForeignKey("search_keyword_sets.id", ondelete="CASCADE"),
        index=True,
    )
    text: Mapped[str] = mapped_column(String(256), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    keyword_set: Mapped[SearchKeywordSet] = relationship(
        "SearchKeywordSet",
        back_populates="keywords",
    )


__all__ = ["SearchKeywordSet", "SearchKeyword"]

