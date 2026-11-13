"""Схемы наборов ключевых слов для API.

Автор: адаптация под TPIS.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SearchKeywordBase(BaseModel):
    """Базовая схема ключевого слова/промпта."""

    text: str
    weight: float = 1.0


class SearchKeywordCreate(SearchKeywordBase):
    """Схема создания ключевого слова."""

    model_config = ConfigDict(extra="forbid")


class SearchKeywordRead(SearchKeywordBase):
    """Схема чтения ключевого слова."""

    id: int

    class Config:
        from_attributes = True


class SearchKeywordSetBase(BaseModel):
    """Базовая схема набора ключевых слов."""

    name: str
    description: str | None = None
    created_by: str | None = None


class SearchKeywordSetCreate(SearchKeywordSetBase):
    """Схема создания набора ключевых слов."""

    keywords: list[SearchKeywordCreate] | None = None

    model_config = ConfigDict(extra="forbid")


class SearchKeywordSetUpdate(BaseModel):
    """Схема обновления набора ключевых слов."""

    name: str | None = None
    description: str | None = None
    created_by: str | None = None
    keywords: list[SearchKeywordCreate] | None = None

    model_config = ConfigDict(extra="forbid")


class SearchKeywordSetRead(SearchKeywordSetBase):
    """Схема чтения набора ключевых слов."""

    id: int
    created_at: datetime
    updated_at: datetime
    keywords: list[SearchKeywordRead] = []

    class Config:
        from_attributes = True


__all__ = [
    "SearchKeywordCreate",
    "SearchKeywordRead",
    "SearchKeywordSetCreate",
    "SearchKeywordSetUpdate",
    "SearchKeywordSetRead",
]

