"""Модель тендера.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, JSON, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tender(Base):
    """Сущность тендера с основными параметрами.

    Атрибуты:
        id: Внутренний идентификатор записи.
        tender_id: Внешний идентификатор тендера.
        title: Наименование закупки.
        region: Регион проведения.
        budget: Бюджет тендера.
        currency: Валюта бюджета.
        status: Статус тендера.
        stage: Стадия тендера/проекта.
        customer: Наименование заказчика.
        winner: Наименование победителя.
        participants: Список участников.
        contacts: Контактные данные контрагентов.
        start_date: Плановая дата начала.
        end_date: Плановая дата окончания.
        source_url: Ссылка на первоисточник.
        quality_flag: Признак качества данных.
        created_at: Дата создания записи.
    """

    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tender_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    region: Mapped[str | None] = mapped_column(String(128))
    budget: Mapped[float | None]
    currency: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str | None] = mapped_column(String(64))
    stage: Mapped[str | None] = mapped_column(String(64))
    customer: Mapped[str | None] = mapped_column(String(256))
    winner: Mapped[str | None] = mapped_column(String(256))
    participants: Mapped[list | None] = mapped_column(JSON)
    contacts: Mapped[dict | None] = mapped_column(JSON)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(512))
    quality_flag: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
