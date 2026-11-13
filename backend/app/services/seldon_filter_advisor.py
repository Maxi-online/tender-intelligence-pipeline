"""Модуль GPT (gpt-5-nano) для подбора настроек фильтров Seldon под цель поиска.

Запросы к OpenAI выполняются только через прокси (OpenAIClient). Для данного
специалиста задан максимальный reasoning_effort для наилучшего качества подбора.

Анализирует цель пользователя (заказчики/победители, тематика, регион) и список
доступных фильтров Seldon, возвращает рекомендуемые filter_id, date_from, date_to,
subtype для максимально точной выгрузки.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты помощник по настройке выгрузки закупок из Seldon. Задача системы — получать максимально свежую информацию о заказчиках и победителях (не участие в тендерах).

На вход даётся:
1) Цель поиска пользователя (свободный текст): тематика, регион, тип закупок (44-ФЗ, 223-ФЗ, коммерческие), акцент на заказчики/победители.
2) Список доступных фильтров учётной записи Seldon: у каждого filterId, name, reportId.
   reportId: 1 = 223-ФЗ, 2 = госзакупки 44/94, 3 = коммерческие, 4 = контракты, 5 = международные.

Ты должен выбрать ОДИН наиболее подходящий фильтр (filterId) по названию и reportId, чтобы выгрузка максимально соответствовала цели. Также предложи разумный период дат (date_from, date_to) в формате ISO 8601 (yyyy-MM-ddTHH:mm:ss.000000+00:00). Для госзакупок 44/94 (reportId=2) можно указать subtype: 1 = ЕИС, 2 = остальные источники (если цель уточняет).

Ответь ТОЛЬКО валидным JSON без markdown и комментариев:
{
  "filter_id": <число, filterId выбранного фильтра>,
  "date_from": "<ISO строка>",
  "date_to": "<ISO строка>",
  "subtype": <1 | 2 | null>,
  "reason": "<краткое обоснование выбора>"
}
Если подходящего фильтра нет — выбери наиболее близкий по смыслу и укажи это в reason."""


def _default_dates() -> tuple[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    return (
        start.strftime("%Y-%m-%dT00:00:00.000000+00:00"),
        end.strftime("%Y-%m-%dT23:59:59.999999+00:00"),
    )


def _parse_llm_response(text: str, filters: list[dict]) -> dict[str, Any]:
    """Распарсить ответ LLM и извлечь filter_id, date_from, date_to, subtype, reason."""
    default_from, default_to = _default_dates()
    out = {
        "filter_id": None,
        "date_from": default_from,
        "date_to": default_to,
        "subtype": None,
        "reason": "",
    }
    raw = text.strip()
    for prefix in ("```json", "```"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):].strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    first_line = raw.split("\n")[0] if "\n" in raw else raw
    try:
        data = json.loads(first_line)
    except json.JSONDecodeError:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return out
    valid_ids = {f.get("filterId") for f in filters if f.get("filterId") is not None}
    fid = data.get("filter_id")
    if fid is not None and (int(fid) if fid is not None else None) in valid_ids:
        out["filter_id"] = int(fid)
    elif filters:
        out["filter_id"] = filters[0].get("filterId")
    if data.get("date_from"):
        out["date_from"] = str(data["date_from"])
    if data.get("date_to"):
        out["date_to"] = str(data["date_to"])
    if data.get("subtype") is not None:
        out["subtype"] = int(data["subtype"]) if data["subtype"] in (1, 2) else None
    if data.get("reason"):
        out["reason"] = str(data["reason"])[:500]
    return out


async def recommend_filter_settings(
    search_goal: str,
    filters: list[dict[str, Any]],
) -> dict[str, Any]:
    """По цели поиска и списку фильтров Seldon вернуть рекомендуемые filter_id, даты, subtype.

    :param search_goal: Цель поиска (свободный текст).
    :param filters: Список из User/Filters: [{"filterId": int, "name": str, "reportId": int}, ...].
    :return: {"filter_id", "date_from", "date_to", "subtype", "reason"}.
    """
    default_from, default_to = _default_dates()
    fallback = {
        "filter_id": filters[0].get("filterId") if filters else None,
        "date_from": default_from,
        "date_to": default_to,
        "subtype": None,
        "reason": "LLM недоступен, использованы умолчания",
    }
    if not filters:
        return {**fallback, "reason": "Нет доступных фильтров"}

    try:
        from app.services.openai_client import OpenAIClient
        client = OpenAIClient()
    except Exception as e:
        logger.warning("Seldon filter advisor: OpenAI unavailable (%s)", e)
        return fallback

    filters_desc = json.dumps(
        [{"filterId": f.get("filterId"), "name": f.get("name"), "reportId": f.get("reportId")} for f in filters],
        ensure_ascii=False,
    )
    user_content = f"Цель поиска: {search_goal}\n\nДоступные фильтры:\n{filters_desc}"

    try:
        try:
            response = await client.chat(
                SYSTEM_PROMPT,
                [{"role": "user", "content": user_content}],
                reasoning_effort="high",
            )
        except Exception as e_high:
            logger.warning("Seldon filter advisor: reasoning_effort=high not supported (%s), retry without", e_high)
            response = await client.chat(SYSTEM_PROMPT, [{"role": "user", "content": user_content}])
        content = response.get("content") or []
        block = content[0] if content else {}
        text_out = block.get("text", "") if isinstance(block, dict) else ""
        if not text_out:
            return fallback
        result = _parse_llm_response(text_out, filters)
        if result.get("filter_id") is None and filters:
            result["filter_id"] = filters[0].get("filterId")
        return result
    except Exception as e:
        logger.exception("Seldon filter advisor call failed: %s", e)
        return fallback
