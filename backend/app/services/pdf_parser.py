"""Parser PDF documents.

Author: Maxi-online
"""

from __future__ import annotations

import io

import pdfplumber


def extract_text_from_pdf(data: bytes) -> str:
    """Extract text from a PDF file.

    :param data: Byte content of PDF.
    :return: PDF text.
    """

    if not data:
        return ""
    buffer = io.BytesIO(data)
    texts = []
    with pdfplumber.open(buffer) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                texts.append(text)
    return "\n".join(texts).strip()
