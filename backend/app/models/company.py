"""The company model.

Author: Maxi-online
"""

from __future__ import annotations

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Company(Base):
    """The nature of the company with the basic contact details.

    Attributes:
        id: Internal record identifier.
        inn: INN company.
        name: Name of company.
        normalized_name: Normalized name to protect against duplicates.
        phone: Contact number.
        email: Contact email.
        address: Address of the company.
        contacts: Additional contacts.
        source_refs: References to data sources.
    """

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inn: Mapped[str | None] = mapped_column(String(12), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    normalized_name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(256))
    address: Mapped[str | None] = mapped_column(String(512))
    contacts: Mapped[dict | None] = mapped_column(JSON)
    source_refs: Mapped[list | None] = mapped_column(JSON)
    canonical_id: Mapped[int | None] = mapped_column(Integer, index=True)
