"""Tender and article communication model.

Author: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MatchLink(Base):
    """Relationship between tender and article with confidence assessment.

    Attributes:
        id: Internal record identifier.
        tender_id: Tender Identifier.
        article_id: Article Identifier.
        confidence_score: Tilt confidence level.
        approved: The operator's confirmation flag.
        reviewed_at: Date of manual confirmation.
        reviewer: Operator &apos; s Identifier.
    """

    __tablename__ = "match_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    confidence_score: Mapped[float] = mapped_column(default=0.0)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewer: Mapped[str | None] = mapped_column(String(128))
