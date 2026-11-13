"""Модель связи тендера и статьи.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MatchLink(Base):
    """Связь между тендером и статьей с оценкой уверенности.

    Атрибуты:
        id: Внутренний идентификатор записи.
        tender_id: Идентификатор тендера.
        article_id: Идентификатор статьи.
        confidence_score: Уровень уверенности в связке.
        approved: Флаг подтверждения оператором.
        reviewed_at: Дата ручного подтверждения.
        reviewer: Идентификатор оператора.
    """

    __tablename__ = "match_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    confidence_score: Mapped[float] = mapped_column(default=0.0)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewer: Mapped[str | None] = mapped_column(String(128))
