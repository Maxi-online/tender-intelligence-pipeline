"""Data source model.

Author: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Source(Base):
    """Materiality of the data source (RSS/HTML/Sitemap/API).

    Attributes:
        id: Internal record identifier.
        name: The human name of the source.
        url: Source reference URL.
        kind: Source type (rss, html, sitamp, api).
        status: Current source status (active, disabled).
        auto_discovered: Sign of autodetection.
        last_checked_at: Date of last check.
        created_at: Date of creation of the record.
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="active")
    auto_discovered: Mapped[bool] = mapped_column(default=False)
    last_checked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
