"""Схемы связи тендера и статьи для API.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MatchLinkBase(BaseModel):
    """Базовая схема связи тендера и статьи.

    Атрибуты:
        tender_id: Идентификатор тендера.
        article_id: Идентификатор статьи.
        confidence_score: Уровень уверенности в связке.
        approved: Флаг подтверждения оператором.
        reviewed_at: Дата подтверждения.
        reviewer: Идентификатор оператора.
    """

    tender_id: int
    article_id: int
    confidence_score: float = 0.0
    approved: bool = False
    reviewed_at: datetime | None = None
    reviewer: str | None = None


class MatchLinkCreate(MatchLinkBase):
    """Схема для создания связи на входе API."""

    model_config = ConfigDict(extra="forbid")


class MatchLinkRead(MatchLinkBase):
    """Схема связи для чтения из API.

    Атрибуты:
        id: Внутренний идентификатор записи.
    """

    id: int

    class Config:
        from_attributes = True
