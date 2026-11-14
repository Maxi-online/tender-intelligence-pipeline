"""The article/news model.

Author: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Article(Base):
    """The essence of an article from an external source.

    Attributes:
        id: Internal record identifier.
        source_id: Source Identifier.
        source: Publication source.
        url: Reference to article.
        title: The title of the article.
        published_at: Date of publication.
        text: Full text of the article.
        entities: Extracted Essentials.
        label: Classification label.
        quality_flag: Data quality sign.
    """

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))
    source: Mapped[str | None] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    published_at: Mapped[datetime | None]
    text: Mapped[str | None] = mapped_column(Text)
    entities: Mapped[dict | None] = mapped_column(JSON)
    label: Mapped[str | None] = mapped_column(String(64))
    quality_flag: Mapped[bool] = mapped_column(Boolean, default=True)
