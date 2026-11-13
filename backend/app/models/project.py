"""Модель проекта.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Project(Base):
    """Сущность строительного проекта.

    Атрибуты:
        id: Внутренний идентификатор записи.
        project_id: Внешний идентификатор проекта.
        name: Название проекта.
        normalized_name: Нормализованное название для защиты от дублей.
        region: Регион реализации.
        stage: Стадия проекта.
        start_date: Плановая дата начала.
        end_date: Плановая дата окончания.
        budget: Оценочная стоимость.
        description: Краткое описание проекта (LLM).
        customer_name: Заказчик.
        customer_email: Email заказчика.
        customer_phone: Телефон заказчика.
        investor_name: Инвестор.
        investor_email: Email инвестора.
        investor_phone: Телефон инвестора.
        contractor_name: Подрядчик.
        contractor_email: Email подрядчика.
        contractor_phone: Телефон подрядчика.
        source_urls: Ссылки на источники проекта.
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    normalized_name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    region: Mapped[str | None] = mapped_column(String(128))
    stage: Mapped[str | None] = mapped_column(String(64))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    budget: Mapped[float | None]
    description: Mapped[str | None] = mapped_column(Text)
    customer_name: Mapped[str | None] = mapped_column(String(256))
    customer_email: Mapped[str | None] = mapped_column(String(256))
    customer_phone: Mapped[str | None] = mapped_column(String(64))
    investor_name: Mapped[str | None] = mapped_column(String(256))
    investor_email: Mapped[str | None] = mapped_column(String(256))
    investor_phone: Mapped[str | None] = mapped_column(String(64))
    contractor_name: Mapped[str | None] = mapped_column(String(256))
    contractor_email: Mapped[str | None] = mapped_column(String(256))
    contractor_phone: Mapped[str | None] = mapped_column(String(64))
    source_urls: Mapped[list[str] | None] = mapped_column(JSON)
