"""Project model.

Author: Maxi-online
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Project(Base):
    """The essence of the construction project.

    Attributes:
        id: Internal record identifier.
        project_id: Project External Identifier.
        name: Name of project.
        normalized_name: Normalized name to protect against duplicates.
        region: Implementation region.
        stage: Project stage.
        start_date: Target date for commencement.
        end_date: Target Date for Completion.
        budget: Estimated value.
        description: Brief description of the project (LLM).
        customer_name: Buyer.
        customer_email: Email by the customer.
        customer_phone: Customer telephone.
        investor_name: Investor.
        investor_email: Email investor.
        investor_phone: Investor &apos; s phone.
        contractor_name: Contractor.
        contractor_email: Email contractor.
        contractor_phone: Contractor &apos; s telephone.
        source_urls: References to project sources.
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
