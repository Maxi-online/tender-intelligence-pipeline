"""Схемы проекта для API.

Автор: Maxi-online
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


from datetime import date


class ProjectBase(BaseModel):
    """Базовая схема проекта.

    Атрибуты:
        project_id: Внешний идентификатор проекта.
        name: Название проекта.
        region: Регион реализации.
        stage: Стадия проекта.
        start_date: Плановая дата начала.
        end_date: Плановая дата окончания.
        budget: Оценочная стоимость.
    """

    project_id: str | None = None
    name: str
    region: str | None = None
    stage: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget: float | None = None
    description: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    investor_name: str | None = None
    investor_email: str | None = None
    investor_phone: str | None = None
    contractor_name: str | None = None
    contractor_email: str | None = None
    contractor_phone: str | None = None
    source_urls: list[str] | None = None


class ProjectCreate(ProjectBase):
    """Схема для создания проекта на входе API."""

    model_config = ConfigDict(extra="forbid")


class ProjectRead(ProjectBase):
    """Схема проекта для чтения из API.

    Атрибуты:
        id: Внутренний идентификатор записи.
    """

    id: int

    class Config:
        from_attributes = True
