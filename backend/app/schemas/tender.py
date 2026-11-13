"""Схемы тендера для API.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TenderBase(BaseModel):
    """Базовая схема тендера.

    Атрибуты:
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
    """

    tender_id: str
    title: str | None = None
    region: str | None = None
    budget: float | None = None
    currency: str | None = None
    status: str | None = None
    stage: str | None = None
    customer: str | None = None
    winner: str | None = None
    participants: list | None = None
    contacts: dict | None = None
    start_date: date | None = None
    end_date: date | None = None
    source_url: str | None = None
    quality_flag: bool = True


class TenderCreate(TenderBase):
    """Схема для создания тендера на входе API."""

    model_config = ConfigDict(extra="forbid")


class TenderRead(TenderBase):
    """Схема тендера для чтения из API.

    Атрибуты:
        id: Внутренний идентификатор записи.
        created_at: Дата создания записи.
    """

    id: int
    created_at: datetime

    class Config:
        from_attributes = True
