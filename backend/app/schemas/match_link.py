"""Tender and article communication schemes for API.

Author: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MatchLinkBase(BaseModel):
    """Basic communication scheme for tenders and articles.

    Attributes:
        tender_id: Tender Identifier.
        article_id: Article Identifier.
        confidence_score: Tilt confidence level.
        approved: The operator's confirmation flag.
        reviewed_at: Date of confirmation.
        reviewer: Operator &apos; s Identifier.
    """

    tender_id: int
    article_id: int
    confidence_score: float = 0.0
    approved: bool = False
    reviewed_at: datetime | None = None
    reviewer: str | None = None


class MatchLinkCreate(MatchLinkBase):
    'A scheme for the API entrance connection.'

    model_config = ConfigDict(extra="forbid")


class MatchLinkRead(MatchLinkBase):
    """The API's read-through scheme.

    Attributes:
        id: Internal record identifier.
    """

    id: int

    class Config:
        from_attributes = True
