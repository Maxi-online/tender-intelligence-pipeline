'Seldon purchase cache model for REST API on TK TPIS.'

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SeldonPurchase(Base):
    """Cash One Seldon Purchase (purchase) for a single REST API.

    Mapping from Purchases/Result and Purchasies/Get; if necessary
    Added from Protocols and Contracts (participants, winner, contacts)).
    """

    __tablename__ = "seldon_purchases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seldon_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notification_number: Mapped[str | None] = mapped_column(String(128))
    subject: Mapped[str | None] = mapped_column(String(1024))
    purchase_price: Mapped[float | None] = mapped_column(Float)
    currency_code: Mapped[str | None] = mapped_column(String(16))
    status_code: Mapped[int | None] = mapped_column(Integer)
    status_name: Mapped[str | None] = mapped_column(String(128))
    stage: Mapped[str | None] = mapped_column(String(128))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    customer_name: Mapped[str | None] = mapped_column(String(512))
    customer_inn: Mapped[str | None] = mapped_column(String(32))
    source_url: Mapped[str | None] = mapped_column(String(512))
    winner_name: Mapped[str | None] = mapped_column(String(512))
    winner_inn: Mapped[str | None] = mapped_column(String(32))
    winner_ogrn: Mapped[str | None] = mapped_column(String(32))
    decision_date: Mapped[date | None] = mapped_column(Date)
    protocol_info: Mapped[dict | list | None] = mapped_column(JSONB)
    participants: Mapped[list | None] = mapped_column(JSONB)
    contact_info: Mapped[dict | list | None] = mapped_column(JSONB)
    raw_purchase: Mapped[dict | None] = mapped_column(JSONB)
    raw_protocol: Mapped[dict | None] = mapped_column(JSONB)
    raw_contract: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
