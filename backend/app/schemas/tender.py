"""Tender schemes for the API.

Author: Maxi-online
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TenderBase(BaseModel):
    """Basic tender scheme.

    Attributes:
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
    'Scheme for the creation of a tender at the API entrance.'

    model_config = ConfigDict(extra="forbid")


class TenderRead(TenderBase):
    """API reading tender scheme.

    Attributes:
        id: Internal record identifier.
        created_at: Date of creation of the record.
    """

    id: int
    created_at: datetime

    class Config:
        from_attributes = True
