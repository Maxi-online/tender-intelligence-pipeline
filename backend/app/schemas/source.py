"""Source diagrams for API.

Author: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SourceBase(BaseModel):
    """Source reference diagram.

    Attributes:
        name: The human name of the source.
        url: Source reference URL.
        kind: Source type (rss, html, sitamp, api).
        status: Source status (active, disabled).
        auto_discovered: Sign of autodetection.
    """

    name: str | None = None
    url: str
    kind: str
    status: str = "active"
    auto_discovered: bool = False


class SourceCreate(SourceBase):
    'Schematic to create a source at the API inlet.'

    model_config = ConfigDict(extra="forbid")


class SourceRead(SourceBase):
    """Schematic of the API reading source.

    Attributes:
        id: Internal record identifier.
        last_checked_at: Date of last check.
        created_at: Date of creation of the record.
    """

    id: int
    last_checked_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True
