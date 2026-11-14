"""Anthropic Claude Sonnet 4.5 client for ranking and classification.

Author: Adaptation to TPIS.
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
    'A simple client of Anthropic Messages API for ranking and classification tasks.'

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
            logger.warning('OPENROUTER_API_KEY is not specified, and fallsback is on OpenAI.')

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
        'Extraction of text from images through Claude Vision.'

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
            'You recognize the text in PDF scans. '
            'Return only extracted text without comments and formatting.'
        )
        content_blocks.append({"type": "text", "text": text_prompt})

        response = await self._call_messages_api(
            system='You are an OCR and text extraction assistant.',
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
        """Land the search results according to relevance.

        :param query: User request.
        :param profiles: List of candidates from Perplexity or other sources.
        :param keywords: Non-mandatory list of domain key words.
        :Return: Same list, but with score field and sorting.
        """

        if not candidates:
            return []

        system = (
            "You're an expert on construction tenders, projects and companies. "
            'Your job is to rank the search results according to the relevance of the request. '
            'Assess only by the logical proximity of the text of the candidates to the request, '
            'without relying on any external lists of key words.'
        )

        # Form a compact JSON nomination.
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
            'Request:\n'
            f"{query}\n\n"
            'Candidates (JSON List):\n'
            f"{items_for_llm}\n\n"
            'Return JSON with the species list '
            '{"id": <id>, "relevance": <from 0 up to 1>, "labels": [<Grades>]} '
            'without any additional text.'
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
        'Normalize the list of projects names for deduplication.'

        unique_titles = [t.strip() for t in titles if t and t.strip()]
        if not unique_titles:
            return {}
        system = (
            'You normalize the names of construction projects for deduplication. '
            'Assess the meaning, sum up the different language of the same draft '
            'to one canonical name. '
            'Return the JSON massage of objects of the species '
            '{"input": "<reference>", "canonical": "<canonical>} without text outside JSON. '
            'Canon name should keep object, location, numbers and unique features. '
            "Don't add fake data."
        )
        user_content = (
            'List of names:\n'
            f"{json.dumps(unique_titles, ensure_ascii=False)}\n\n"
            'Just return the JSON massage of the objects.'
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
        'Normalization of the project name for deduplication.'

        mapping = await self.normalize_project_titles([title])
        canonical = mapping.get(title, "").strip()
        if not canonical:
            return ""
        if len(canonical) > 200:
            canonical = canonical[:200]
        return canonical

    async def classify_project_titles(self, titles: list[str]) -> dict[str, bool]:
        'Identify noisy/non-project names via LLM.'

        unique_titles = [t.strip() for t in titles if t and t.strip()]
        if not unique_titles:
            return {}
        system = (
            'You classify the lines as real names of construction projects/tenders '
            'or noise (events of events, advertising, general phrases without object)). '
            'Return the JSON massage of objects of the species '
            '{"Input": "<string>", "is_noise": trie/false} without text outside JSON. '
            'If you doubt it, mark is_noise=false; cut off only the clear noise.'
        )
        user_content = (
            'List of rows:\n'
            f"{json.dumps(unique_titles, ensure_ascii=False)}\n\n"
            'Just return the JSON massage of the objects.'
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
        'Formulate a brief description of the draft on the basis of the text.'

        if not text.strip():
            return ""
        system = (
            "You're a systems analyst for construction projects. "
            'Form a brief description of the draft (2-4 sentences) strictly within the meaning of the text: '
            'Subject matter, location, stage, budget, employer/contractor. '
            "If there's no data, don't make it up."
        )
        user = (
            f"Name: {title}\n"
            'Text:\n'
            f"{text}\n\n"
            'Just give me the description without the lists and no more water.'
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

