"""Пайплайн обработки PDF: извлечение текста и разбиение на фрагменты.

Если в PDF нет текстового слоя (или его слишком мало), возвращается пустой список фрагментов.
"""

from __future__ import annotations

import io
from typing import Any

import pdfplumber

from app.services.claude_client import ClaudeClient


def _split_plain_text(text: str, max_chars: int = 4000) -> list[str]:
    """Разбить длинный текст на фрагменты по абзацам.

    :param text: Исходный текст.
    :param max_chars: Максимальная длина одного фрагмента.
    :return: Список фрагментов.
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
    """Извлечь текст из PDF.

    :param data: Байтовое содержимое PDF.
    :return: Словарь с полями:
        - mode: "text" или "vision"
        - fragments: список текстовых фрагментов
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

    # Если текстового слоя нет — пытаемся извлечь через Claude Vision (OCR).
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

