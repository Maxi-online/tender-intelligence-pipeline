"""Models of keyword sets to search for.

Author: Adaptation to TPIS.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SearchKeywordSet(Base):
    """Set of key words/prompts for search scenarios.

    Attributes:
        id: Internal recruitment identifier.
        name: Human-readable name.
        description: Description of the purpose of the kit.
        created_by: Author &apos; s Identifier (arbitrary line).
        created_at: Date/time of creation.
        updated_at: Date/time of last update.
    """

    __tablename__ = "search_keyword_sets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    keywords: Mapped[list["SearchKeyword"]] = relationship(
        "SearchKeyword",
        back_populates="keyword_set",
        cascade="all, delete-orphan",
    )


class SearchKeyword(Base):
    """Specific key word/prompt in the selection.

    Attributes:
        id: Internal identifier.
        set_id: Set Identifier.
        text: Keyword or propt.
        weight: Weight/priority (default 1.0).
    """

    __tablename__ = "search_keywords"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(
        ForeignKey("search_keyword_sets.id", ondelete="CASCADE"),
        index=True,
    )
    text: Mapped[str] = mapped_column(String(256), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    keyword_set: Mapped[SearchKeywordSet] = relationship(
        "SearchKeywordSet",
        back_populates="keywords",
    )


__all__ = ["SearchKeywordSet", "SearchKeyword"]

