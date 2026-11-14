"""Articles for the API.

Author: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArticleBase(BaseModel):
    """The basic outline of the article.

    Attributes:
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

    source_id: int | None = None
    source: str | None = None
    url: str
    title: str | None = None
    published_at: datetime | None = None
    text: str | None = None
    entities: dict | None = None
    label: str | None = None
    quality_flag: bool = True


class ArticleCreate(ArticleBase):
    'Scheme for the creation of an article at the API entrance.'

    model_config = ConfigDict(extra="forbid")


class ArticleRead(ArticleBase):
    """Schematic of an article to read from API.

    Attributes:
        id: Internal record identifier.
    """

    id: int

    class Config:
        from_attributes = True
