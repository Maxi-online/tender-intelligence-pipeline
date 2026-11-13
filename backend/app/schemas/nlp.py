"""Схемы NLP API.

Автор: Maxi-online
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TextRequest(BaseModel):
    """Схема запроса с текстом.

    Атрибуты:
        text: Входной текст для обработки.
    """

    text: str


class TextRequestCreate(TextRequest):
    """Схема для NLP запросов на входе API."""

    model_config = ConfigDict(extra="forbid")

