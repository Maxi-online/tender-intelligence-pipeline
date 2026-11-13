"""Мультиагентная проверка качества выгрузки Seldon: соответствие тематике и требованиям ТЗ.

Опциональный шаг после получения Purchases/Result: несколько LLM (или одна модель)
оценивают каждую закупку по критериям (строительная/инфраструктурная тематика,
наличие обязательных полей, отсутствие мусора). Записи, не прошедшие проверку,
можно не сохранять или помечать флагом.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.seldon_service import map_purchase_to_tpis_schema

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты строгий классификатор закупок для системы TPIS.
Оцени закупку по критериям:
1) Тематика: строительство, реконструкция, капремонт, инфраструктура (дороги, мосты, сети), объекты соцкультбыта (школы, больницы, детсады). Если тематика явно не строительная/инфраструктурная — верни "reject".
2) Обязательные поля: наличие осмысленного названия и заказчика (или организатора). Если названия нет или это явный мусор (контакты, форма вопрос-ответ, реклама) — верни "reject".
3) Мусор: отклони закупки по продаже макулатуры, металлолома, запчастей, канцелярии, если это не связано со строительством объекта.

Ответь ТОЛЬКО валидным JSON вида: {"verdict": "accept" | "reject", "reason": "краткое обоснование"}."""


async def validate_purchases_with_llm(
    purchases: list[dict[str, Any]],
    *,
    max_batch_size: int = 20,
) -> list[tuple[dict[str, Any], bool, str]]:
    """Проверить список закупок через LLM. Возвращает для каждой (purchase, passed, reason)."""
    try:
        from app.services.openai_client import OpenAIClient
        client = OpenAIClient()
    except Exception as e:
        logger.warning("Seldon validation: OpenAI client unavailable (%s), skip validation", e)
        return [(p, True, "validation skipped") for p in purchases]

    results: list[tuple[dict[str, Any], bool, str]] = []
    for i in range(0, len(purchases), max_batch_size):
        batch = purchases[i : i + max_batch_size]
        for raw in batch:
            try:
                schema = map_purchase_to_tpis_schema(raw)
                text = f"Название: {schema.get('title') or ''}\nЗаказчик: {schema.get('customer') or ''}\nНомер: {schema.get('notification_number') or ''}"
                response = await client.chat(SYSTEM_PROMPT, [{"role": "user", "content": text}])
                content = (response.get("content") or [])
                block = content[0] if content else {}
                text_out = block.get("text", "{}") if isinstance(block, dict) else "{}"
                if isinstance(text_out, list):
                    text_out = text_out[0] if text_out else "{}"
                raw_json = text_out.strip()
                for prefix in ("```json", "```"):
                    if raw_json.startswith(prefix):
                        raw_json = raw_json[len(prefix):].strip()
                    if raw_json.endswith("```"):
                        raw_json = raw_json[:-3].strip()
                data = json.loads(raw_json.split("\n")[0] if "\n" in raw_json else raw_json)
                verdict = (data.get("verdict") or "").lower()
                reason = data.get("reason") or ""
                passed = verdict == "accept"
                results.append((raw, passed, reason))
            except Exception as e:
                logger.warning("Seldon validation item failed: %s", e)
                results.append((raw, True, f"validation error: {e}"))
    return results


def filter_purchases_by_validation(
    purchases: list[dict[str, Any]],
    validation_results: list[tuple[dict[str, Any], bool, str]],
) -> list[dict[str, Any]]:
    """Оставить только закупки, прошедшие проверку."""
    passed_ids = {id(raw) for raw, passed, _ in validation_results if passed}
    return [p for p in purchases if id(p) in passed_ids]
