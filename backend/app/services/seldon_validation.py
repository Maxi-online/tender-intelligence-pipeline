"""Multi-agent quality check for the discharge of Seldon: compliance with the subject matter and requirements of TK.

Option step after Purchasing/Result: Several LLM (or one model))
Assess each procurement by criteria (construction/infrastructure topics),
Mandatory fields, no garbage). Records not tested,
may not hold or mark the flag.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.seldon_service import map_purchase_to_tpis_schema

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = 'You\'re a strict procurement classification for the TPIS system.\nAssess procurement against criteria:\n1) Themes: construction, reconstruction, capremont, infrastructure (roads, bridges, networks), objects of social culture (schools, hospitals, kindergartens)). If the subject is clearly not construction/infrastructure, return "project"".\n(2) Mandatory fields: meaningful name and customer (or organizer)). If there\'s no name, or if it\'s plain trash (comments, form of question-and-answer, advertising) - give back the "project"".\n3) Waste: disadvantages of purchase for sale of machulature, metal, spare parts, office, if this is not related to the construction of the object.\n\nAnswer the only one who\'s valid JSON species: {"verdict": "accept" | "reject", "reason": "brief justification"}.'


async def validate_purchases_with_llm(
    purchases: list[dict[str, Any]],
    *,
    max_batch_size: int = 20,
) -> list[tuple[dict[str, Any], bool, str]]:
    'Check the procurement list with LLM. Returns for each (purchase, passed, reason)).'
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
                text = f"Name: {schema.get('title') or ''}\n Buyer: {schema.get('customer') or ''}\n Number: {schema.get('notification_number') or ''}"
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
    'Leave only those purchases that have been tested.'
    passed_ids = {id(raw) for raw, passed, _ in validation_results if passed}
    return [p for p in purchases if id(p) in passed_ids]
