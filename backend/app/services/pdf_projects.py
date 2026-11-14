"""Extraction of projects from a large PDF with Claude.

Objective: To find a long text (recognised from the journal/report)
maximum unique construction projects and return their brief descriptions.
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
    """Extract a list of projects names/formulations from the PDF text.

    Using Claude Sonnet 4.5, requesting the return of the JSON line massage.
    """

    if not fragments:
        return []
    combined = "\n\n".join(fragments).strip()
    if not combined or len(combined) < 200:
        return []
    chunks = _split_text(combined)

    system = (
        "You're an expert in building logs and reports. "
        'Your job is to find all references to stand-alone construction projects in the text '
        '(Roads, bridges, pipelines, railways, factories, complexes, etc.). '
        'Do not include tenders as legal procedures, i.e. description of construction sites.'
    )
    claude = ClaudeClient()
    results: list[str] = []
    import json

    for chunk in chunks:
        user = (
            'The list of unique construction projects.\n'
            'Each element of the list is a CREDENTIAL OF THE PROJECT (1 line) without any further details.\n'
            'Return the NET JSON string array, no comment and no additional text.\n\n'
            'Text:\n'
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

    # Deduplicate and clean
    deduped: list[str] = []
    seen = set()
    for item in results:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


__all__ = ["extract_project_names_with_claude"]

