"""Клиент Anthropic Claude Sonnet 4.5 для ранжирования и классификации.

Автор: адаптация под TPIS.
"""

from __future__ import annotations

from typing import Any, Literal, Sequence

import base64
import json
import logging
import re
import time

import httpx

from app.core.config import get_settings
from app.services.openai_client import OpenAIClient

logger = logging.getLogger(__name__)


ClaudeModel = Literal["claude-3-5-sonnet-20241022"]


class ClaudeClient:
    """Простой клиент Anthropic Messages API под задачи ранжирования и классификации."""

    def __init__(self) -> None:
        settings = get_settings()
        self._proxy_url: str | None = getattr(settings, "http_proxy_url", None)
        self._model: ClaudeModel = getattr(
            settings,
            "anthropic_model",
            "claude-3-5-sonnet-20241022",
        )

        self._openrouter_api_key: str | None = getattr(settings, "openrouter_api_key", None)
        self._openrouter_base_url: str = getattr(
            settings,
            "openrouter_base_url",
            "https://openrouter.ai/api/v1",
        ).rstrip("/")
        self._openrouter_model: str = getattr(settings, "openrouter_model", None) or self._model
        self._openrouter_app_url: str | None = getattr(settings, "openrouter_app_url", None)
        self._openrouter_app_name: str | None = getattr(settings, "openrouter_app_name", None)

        self._use_openrouter = True
        self._openai_client: OpenAIClient | None = None
        self._openrouter_disabled_until = 0.0
        self._openrouter_backoff_seconds = 600.0
        self._force_openai = True
        if not self._openrouter_api_key:
            logger.warning("OPENROUTER_API_KEY не задан, включен fallback на OpenAI.")

    async def _call_messages_api(
        self,
        system: str,
        messages: Sequence[dict[str, Any]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        if self._force_openai:
            if self._openai_client is None:
                self._openai_client = OpenAIClient()
            return await self._openai_client.chat(
                system,
                list(messages),
            )
        if not self._openrouter_api_key or time.monotonic() < self._openrouter_disabled_until:
            if self._openai_client is None:
                self._openai_client = OpenAIClient()
            return await self._openai_client.chat(
                system,
                list(messages),
            )
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._openrouter_api_key or ''}",
            "Content-Type": "application/json",
        }
        if self._openrouter_app_url:
            headers["HTTP-Referer"] = self._openrouter_app_url
        if self._openrouter_app_name:
            headers["X-Title"] = self._openrouter_app_name

        payload: dict[str, Any] = {
            "model": self._openrouter_model,
            "messages": [{"role": "system", "content": system}, *list(messages)],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=60.0, proxy=self._proxy_url) as client:
                response = await client.post(
                    f"{self._openrouter_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
            data = response.json()
            content: Any = ""
            try:
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            except Exception:  # noqa: BLE001
                content = ""
            if isinstance(content, list):
                content = "\n".join(str(item) for item in content)
            return {"content": [{"type": "text", "text": str(content)}]}
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 402:
                self._openrouter_disabled_until = time.monotonic() + self._openrouter_backoff_seconds
                logger.warning(
                    "OpenRouter 402: fallback to OpenAI for %.0f seconds",
                    self._openrouter_backoff_seconds,
                )
            else:
                logger.warning("OpenRouter failed, fallback to OpenAI: %s", exc)
            if self._openai_client is None:
                self._openai_client = OpenAIClient()
            return await self._openai_client.chat(
                system,
                list(messages),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenRouter failed, fallback to OpenAI: %s", exc)
            if self._openai_client is None:
                self._openai_client = OpenAIClient()
            return await self._openai_client.chat(
                system,
                list(messages),
            )

    async def extract_text_from_images(
        self,
        images: list[bytes],
        *,
        prompt: str | None = None,
        max_tokens: int = 2048,
    ) -> str:
        """Извлечь текст из изображений через Claude Vision."""

        if not images:
            return ""

        content_blocks: list[dict[str, Any]] = []
        for image in images:
            encoded = base64.b64encode(image).decode("ascii")
            if self._use_openrouter:
                content_blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    }
                )
            else:
                content_blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": encoded,
                        },
                    }
                )

        text_prompt = prompt or (
            "Ты распознаешь текст в сканах PDF. "
            "Верни только извлеченный текст без комментариев и форматирования."
        )
        content_blocks.append({"type": "text", "text": text_prompt})

        response = await self._call_messages_api(
            system="Ты помощник для OCR и извлечения текста.",
            messages=[{"role": "user", "content": content_blocks}],
            max_tokens=max_tokens,
            temperature=0.0,
        )

        content = response.get("content") or []
        text_blocks = [block.get("text") for block in content if block.get("type") == "text"]
        return "\n".join(t for t in text_blocks if t)

    async def rank_results(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        keywords: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Отранжировать результаты поиска по релевантности.

        :param query: Пользовательский запрос.
        :param candidates: Список кандидатов от Perplexity или других источников.
        :param keywords: Необязательный список доменных ключевых слов.
        :return: Тот же список, но с полем score и сортировкой по убыванию.
        """

        if not candidates:
            return []

        system = (
            "Ты эксперт по строительным тендерам, проектам и компаниям. "
            "Твоя задача — ранжировать результаты поиска по релевантности запросу. "
            "Оценивай только по смысловой близости текста кандидатов к запросу, "
            "не опираясь на какие-либо внешние списки ключевых слов."
        )

        # Формируем компактное JSON-представление кандидатов.
        items_for_llm: list[dict[str, Any]] = []
        for idx, item in enumerate(candidates, start=1):
            items_for_llm.append(
                {
                    "id": idx,
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("snippet"),
                    "score_hint": item.get("score"),
                }
            )

        user_content = (
            "Запрос:\n"
            f"{query}\n\n"
            "Кандидаты (список JSON-объектов):\n"
            f"{items_for_llm}\n\n"
            "Верни JSON со списком объектов вида "
            '{"id": <id>, "relevance": <от 0 до 1>, "labels": [<классы>]} '
            "без какого-либо дополнительного текста."
        )

        response = await self._call_messages_api(
            system=system,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=1024,
            temperature=0.0,
        )

        content = response.get("content") or []
        if not content:
            return candidates

        text_blocks = [block.get("text") for block in content if block.get("type") == "text"]
        merged = "\n".join(t for t in text_blocks if t)

        try:
            import json

            parsed = json.loads(merged)
            ranking: list[dict[str, Any]] = parsed if isinstance(parsed, list) else parsed.get("items", [])
        except Exception:  # noqa: BLE001
            return candidates

        relevance_by_id: dict[int, dict[str, Any]] = {}
        for item in ranking:
            try:
                cid = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            relevance_by_id[cid] = {
                "relevance": float(item.get("relevance", 0.0)),
                "labels": item.get("labels") or [],
            }

        enriched: list[dict[str, Any]] = []
        for idx, item in enumerate(candidates, start=1):
            extra = relevance_by_id.get(idx, {})
            enriched.append(
                {
                    **item,
                    "score": float(extra.get("relevance", item.get("score", 0.0))),
                    "labels": extra.get("labels", []),
                }
            )

        enriched.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return enriched

    def _extract_json(self, text: str) -> Any | None:
        for match in re.finditer(r"(\{.*\}|\[.*\])", text, re.DOTALL):
            chunk = match.group(1)
            try:
                return json.loads(chunk)
            except Exception:  # noqa: BLE001
                continue
        return None

    async def normalize_project_titles(self, titles: list[str]) -> dict[str, str]:
        """Нормализовать список названий проектов для дедупликации."""

        unique_titles = [t.strip() for t in titles if t and t.strip()]
        if not unique_titles:
            return {}
        system = (
            "Ты нормализуешь названия строительных проектов для дедупликации. "
            "Оценивай смысл, своди разные формулировки одного и того же проекта "
            "к одному каноническому названию. "
            "Верни JSON-массив объектов вида "
            '{"input": "<исходное>", "canonical": "<каноническое>"} без текста вне JSON. '
            "Каноническое имя должно сохранять объект, локации, номера и уникальные признаки. "
            "Не добавляй выдуманные данные."
        )
        user_content = (
            "Список названий (JSON-массив строк):\n"
            f"{json.dumps(unique_titles, ensure_ascii=False)}\n\n"
            "Верни только JSON-массив объектов."
        )
        response = await self._call_messages_api(
            system=system,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=2048,
            temperature=0.0,
        )
        content = response.get("content") or []
        text_blocks = [block.get("text") for block in content if block.get("type") == "text"]
        merged = "\n".join(t for t in text_blocks if t)
        parsed = self._extract_json(merged)
        if not isinstance(parsed, list):
            return {}
        result: dict[str, str] = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            original = str(item.get("input") or "").strip()
            canonical = str(item.get("canonical") or "").strip()
            canonical = canonical.strip("\"'«»")
            if original:
                result[original] = canonical
        return result

    async def normalize_project_title(self, title: str) -> str:
        """Нормализовать название проекта для дедупликации."""

        mapping = await self.normalize_project_titles([title])
        canonical = mapping.get(title, "").strip()
        if not canonical:
            return ""
        if len(canonical) > 200:
            canonical = canonical[:200]
        return canonical

    async def classify_project_titles(self, titles: list[str]) -> dict[str, bool]:
        """Определить шумные/непроектные названия через LLM."""

        unique_titles = [t.strip() for t in titles if t and t.strip()]
        if not unique_titles:
            return {}
        system = (
            "Ты классифицируешь строки как реальные названия строительных проектов/тендеров "
            "или шум (анонсы мероприятий, реклама, общие фразы без объекта). "
            "Верни JSON-массив объектов вида "
            '{"input": "<строка>", "is_noise": true/false} без текста вне JSON. '
            "Если сомневаешься — помечай is_noise=false (оставляй в списке); отсекай только явный шум."
        )
        user_content = (
            "Список строк (JSON-массив строк):\n"
            f"{json.dumps(unique_titles, ensure_ascii=False)}\n\n"
            "Верни только JSON-массив объектов."
        )
        response = await self._call_messages_api(
            system=system,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=2048,
            temperature=0.0,
        )
        content = response.get("content") or []
        text_blocks = [block.get("text") for block in content if block.get("type") == "text"]
        merged = "\n".join(t for t in text_blocks if t)
        parsed = self._extract_json(merged)
        if not isinstance(parsed, list):
            return {}
        result: dict[str, bool] = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            original = str(item.get("input") or "").strip()
            is_noise = bool(item.get("is_noise"))
            if original:
                result[original] = is_noise
        return result

    async def summarize_project(self, title: str, text: str) -> str:
        """Сформировать краткое описание проекта на основе текста."""

        if not text.strip():
            return ""
        system = (
            "Ты системный аналитик строительных проектов. "
            "Сформируй краткое описание проекта (2-4 предложения) строго по смыслу текста: "
            "объект, локация, стадия, бюджет, заказчик/подрядчик. "
            "Если данных нет, не выдумывай."
        )
        user = (
            f"Название: {title}\n"
            "Текст:\n"
            f"{text}\n\n"
            "Верни только описание без списков и без лишней воды."
        )
        response = await self._call_messages_api(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=256,
            temperature=0.2,
        )
        content = response.get("content") or []
        text_blocks = [block.get("text") for block in content if block.get("type") == "text"]
        summary = " ".join(t for t in text_blocks if t).strip()
        return summary[:1000]


__all__ = ["ClaudeClient"]

