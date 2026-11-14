"""NLP API schemes.

Author: Maxi-online
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TextRequest(BaseModel):
    """Schematic of request with text.

    Attributes:
        text: Input text for processing.
    """

    text: str


class TextRequestCreate(TextRequest):
    'The chart for the NLP requests at the API inlet.'

    model_config = ConfigDict(extra="forbid")

