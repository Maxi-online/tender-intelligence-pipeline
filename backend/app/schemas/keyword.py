"""Schematics of Keyword Sets for API.

Author: Adaptation to TPIS.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SearchKeywordBase(BaseModel):
    'Basic key word/prompt diagram.'

    text: str
    weight: float = 1.0


class SearchKeywordCreate(SearchKeywordBase):
    'A key word scheme.'

    model_config = ConfigDict(extra="forbid")


class SearchKeywordRead(SearchKeywordBase):
    'A keyword reading scheme.'

    id: int

    class Config:
        from_attributes = True


class SearchKeywordSetBase(BaseModel):
    'Basic outline of a set of key words.'

    name: str
    description: str | None = None
    created_by: str | None = None


class SearchKeywordSetCreate(SearchKeywordSetBase):
    'Schematic of the creation of a set of key words.'

    keywords: list[SearchKeywordCreate] | None = None

    model_config = ConfigDict(extra="forbid")


class SearchKeywordSetUpdate(BaseModel):
    'Scheme for updating the set of key words.'

    name: str | None = None
    description: str | None = None
    created_by: str | None = None
    keywords: list[SearchKeywordCreate] | None = None

    model_config = ConfigDict(extra="forbid")


class SearchKeywordSetRead(SearchKeywordSetBase):
    'Schematic of reading a set of key words.'

    id: int
    created_at: datetime
    updated_at: datetime
    keywords: list[SearchKeywordRead] = []

    class Config:
        from_attributes = True


__all__ = [
    "SearchKeywordCreate",
    "SearchKeywordRead",
    "SearchKeywordSetCreate",
    "SearchKeywordSetUpdate",
    "SearchKeywordSetRead",
]

