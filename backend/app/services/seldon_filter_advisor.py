"""GPT (gpt-5-nano) module to select Seldon filter settings for search purposes.

Requests for OpenAI are only executed via Proxi (OpenAIClient)). For this
Maximum reasoning_effort specified for best rebound quality.

Analyses user purpose (buyers/winners, subject matter, region) and list
Seldon filters available, returns recommended filter_id, date_from, date_to,
subtype for as precise a discharge as possible.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = 'You\'re a Seldon offloading assistant. The purpose of the system is to obtain the most up-to-date information on customers and winners (not participating in tenders)).\n\nThe entrance shall be:\n1) Purpose of user search (free text): theme, region, type of purchases (44-FZ, 223-FZ, commercial), emphasis on customers/winners.\n(2) List of available Seldon account filters: each filterId, name, reportId.\n   reportId: 1 = 223-FZ, 2 = public procurement 44/94, 3 = commercial, 4 = contracts, 5 = international.\n\nYou need to choose the most suitable filter (filterId) by name and reportId so that the charging corresponds to the target as much as possible. Also propose a reasonable period of dates (date_from, date_to) in ISO 8601 format (yyyy-MM-ddTHH:mm:ss.000000+0000)). For public procurement 44/94 (reportId=2) you can specify subtype: 1 = EIS, 2 = other sources (if the target specifies)).\n\nAnswer JSON\'s only valide without Markdown and comments:\n{\n  "filter_id": <number, filterId selected filter>,\n  "date_from": "<ISO Line>",\n  "date_to": "<ISO Line>",\n  "subtype": <1 | 2 | null>,\n  "reason": "<A brief justification for the choice>"\n}\nIf you don\'t have a suitable filter, choose the closest one in the sense and point it out in reason.'


def _default_dates() -> tuple[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    return (
        start.strftime("%Y-%m-%dT00:00:00.000000+00:00"),
        end.strftime("%Y-%m-%dT23:59:59.999999+00:00"),
    )


def _parse_llm_response(text: str, filters: list[dict]) -> dict[str, Any]:
    'Disperse the LLM answer and extract filter_id, date_from, date_to, subtype, reason.'
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
    """For search and list of Seldon filters, return the recommended filter_id, dates, subtype.

    :param search_goal: Search Purpose (free text).
    :param filters: List from User/Filters: [{"filterId": int, "name": str, "reportId": int}, ...].
    :return: {"filter_id", "date_from", "date_to", "subtype", "reason"}.
    """
    default_from, default_to = _default_dates()
    fallback = {
        "filter_id": filters[0].get("filterId") if filters else None,
        "date_from": default_from,
        "date_to": default_to,
        "subtype": None,
        "reason": 'LLM is not accessible, silences are used',
    }
    if not filters:
        return {**fallback, "reason": 'No accessible filters'}

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
    user_content = f"Search Purpose: {search_goal}\n\n Accessable filters:\n{filters_desc}"

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
