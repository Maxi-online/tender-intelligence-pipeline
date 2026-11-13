"""Извлечение проектов из большого PDF с помощью Claude.

Задача: по длинному тексту (распознанному из журнала/отчёта) найти
максимум уникальных строительных проектов и вернуть их краткие описания.
"""

from __future__ import annotations

from typing import Any

from app.services.claude_client import ClaudeClient


def _split_text(text: str, max_chars: int = 8000) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    current: list[str] = []
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


async def extract_project_names_with_claude(fragments: list[str]) -> list[str]:
    """Извлечь список названий/формулировок проектов из текста PDF.

    Использует Claude Sonnet 4.5, просит вернуть JSON-массив строк.
    """

    if not fragments:
        return []
    combined = "\n\n".join(fragments).strip()
    if not combined or len(combined) < 200:
        return []
    chunks = _split_text(combined)

    system = (
        "Ты эксперт по анализу строительных журналов и отчетов. "
        "Твоя задача — найти в тексте все упоминания ОТДЕЛЬНЫХ строительных проектов "
        "(автомобильные дороги, мосты, путепроводы, железнодорожные пути, заводы, комплексы и т.п.). "
        "Не включай тендеры как юридические процедуры, а именно описания объектов строительства."
    )
    claude = ClaudeClient()
    results: list[str] = []
    import json

    for chunk in chunks:
        user = (
            "Извлеки из приведённого текста список уникальных проектов строительства.\n"
            "Каждый элемент списка — КРАТКАЯ формулировка проекта (1 строка), без лишних деталей.\n"
            "Верни ЧИСТЫЙ JSON массив строк, без комментариев и дополнительного текста.\n\n"
            "Текст:\n"
            f"{chunk}"
        )
        response = await claude._call_messages_api(  # type: ignore[attr-defined]
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=1024,
            temperature=0.1,
        )
        content = response.get("content") or []
        text_blocks = [b.get("text") for b in content if b.get("type") == "text"]
        merged = "\n".join(t for t in text_blocks if t)
        try:
            data = json.loads(merged)
            if isinstance(data, list):
                results.extend([str(item).strip() for item in data if str(item).strip()])
        except Exception:  # noqa: BLE001
            continue

    # Уникализируем и чистим
    deduped: list[str] = []
    seen = set()
    for item in results:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


__all__ = ["extract_project_names_with_claude"]

