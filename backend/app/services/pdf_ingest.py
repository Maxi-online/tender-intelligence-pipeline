"""PDF Processing Plane: Text Extraction and Fragmenting.

If there is no text layer in the PDF (or too few), an empty list of fragments returns.
"""

from __future__ import annotations

import io
from typing import Any

import pdfplumber

from app.services.claude_client import ClaudeClient


def _split_plain_text(text: str, max_chars: int = 4000) -> list[str]:
    """Split the long text into fragments into paragraphs.

    :param text: Reference text.
    :param max_chars: Maximum length of one fragment.
    List of fragments.
    """

    if not text:
        return []
    chunks: list[str] = []
    current = []
    current_len = 0
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current_len + len(paragraph) + 2 > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len += len(paragraph) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def extract_text_smart(data: bytes) -> dict[str, Any]:
    """Extract text from a PDF.

    :param data: Byte content of PDF.
    :return: Field dictionary:
        - Mode: "text" or "vision"
        - Fragments: list of text pieces
    """

    if not data:
        return {"mode": "text", "fragments": []}

    buffer = io.BytesIO(data)
    plain_text_pages: list[str] = []
    with pdfplumber.open(buffer) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                plain_text_pages.append(text)

    merged_text = "\n\n".join(plain_text_pages).strip()
    if merged_text:
        return {"mode": "text", "fragments": _split_plain_text(merged_text)}

    # If there is no text layer, we try to extract through Claude Vision (OCR)).
    try:
        images: list[bytes] = []
        buffer.seek(0)
        with pdfplumber.open(buffer) as pdf:
            for idx, page in enumerate(pdf.pages):
                try:
                    page_image = page.to_image(resolution=150)
                    pil_image = getattr(page_image, "original", None) or getattr(
                        page_image, "image", None
                    )
                    if pil_image is None:
                        continue
                    img_buf = io.BytesIO()
                    pil_image.save(img_buf, format="PNG")
                    images.append(img_buf.getvalue())
                except Exception:  # noqa: BLE001
                    continue

        if not images:
            return {"mode": "text", "fragments": []}

        client = ClaudeClient()
        ocr_text = await client.extract_text_from_images(images)
        fragments = _split_plain_text(ocr_text)
        if fragments:
            return {"mode": "vision", "fragments": fragments}
    except Exception:  # noqa: BLE001
        pass

    return {"mode": "text", "fragments": []}


__all__ = ["extract_text_smart"]

