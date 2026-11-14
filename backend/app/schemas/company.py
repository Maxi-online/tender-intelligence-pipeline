"""Company schemes for API.

Author: Maxi-online
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CompanyBase(BaseModel):
    """The company's basic scheme.

    Attributes:
        inn: INN company.
        name: Name of company.
        phone: Contact number.
        email: Contact email.
        address: Address of the company.
        contacts: Additional contacts.
        source_refs: References to data sources.
        canonical_id: Identifier of the canon company.
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
    'A scheme to create a company at the API entrance.'

    model_config = ConfigDict(extra="forbid")


class CompanyRead(CompanyBase):
    """The company's chart for reading from API.

    Attributes:
        id: Internal record identifier.
    """

    id: int

    class Config:
        from_attributes = True
