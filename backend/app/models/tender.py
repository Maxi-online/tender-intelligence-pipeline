"""The tender model.

Author: Maxi-online
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, JSON, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tender(Base):
    """The nature of the tender with the basic parameters.

    Attributes:
        id: Internal record identifier.
        tender_id: External tender identifier.
        title: Purchase name.
        region: Implementation region.
        budget: Tender budget.
        currency: Currency of the budget.
        status: Bidding status.
        stage: tender/project stage.
        customer: Name of customer.
        winner: Name of winner.
        participants: List of participants.
        contacts: Contact details of the counterparties.
        start_date: Target date for commencement.
        end_date: Target Date for Completion.
        source_url: Reference to source.
        quality_flag: Data quality sign.
        created_at: Date of creation of the record.
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
