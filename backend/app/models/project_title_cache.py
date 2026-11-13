"""Кэш канонических названий проектов.

Автор: адаптация под TPIS.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProjectTitleCache(Base):
    """Кэш канонических названий проектов для дедупликации."""

    __tablename__ = "project_title_cache"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    original_title: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    canonical_title: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
    )
