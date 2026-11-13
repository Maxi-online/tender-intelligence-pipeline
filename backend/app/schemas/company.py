"""Схемы компании для API.

Автор: Maxi-online
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CompanyBase(BaseModel):
    """Базовая схема компании.

    Атрибуты:
        inn: ИНН компании.
        name: Наименование компании.
        phone: Контактный телефон.
        email: Контактный email.
        address: Адрес компании.
        contacts: Дополнительные контакты.
        source_refs: Ссылки на источники данных.
        canonical_id: Идентификатор канонической компании.
    """

    inn: str | None = None
    name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    contacts: dict | None = None
    source_refs: list | None = None
    canonical_id: int | None = None


class CompanyCreate(CompanyBase):
    """Схема для создания компании на входе API."""

    model_config = ConfigDict(extra="forbid")


class CompanyRead(CompanyBase):
    """Схема компании для чтения из API.

    Атрибуты:
        id: Внутренний идентификатор записи.
    """

    id: int

    class Config:
        from_attributes = True
