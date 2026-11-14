"""Perplexity API client for text/web search.

Perplexity is used for:
- Searching for projects, tenders and state orders (ingest_perplexity_leads): Key words
  and "44-FZ 223-FZ" requests refer to articles/pages, parsim and database.
- Search for Sources (DiscoveryService): Search for new RSS/portals according to key words.
- User search (semantic_search): Primary collection of results, then ranking of Claude.
- Company Enrichment: Searching for Companies (Rusprofile et al.).).

Author: Maxi-online (adaptation to LLM search).
"""

from __future__ import annotations

from typing import Any

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class PerplexityClient:
    """The client Perplexity Chat Compilations API.

    IMPORTANT: Perplexity always uses SWI models (Sonar family)).
    Claude in Perplexity cannot be launched for Claude Sonnet 4.5
    We have a separate client, Anthropic (`ClaudeClient`).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str | None = getattr(settings, "perplexity_api_key", None)
        self._proxy_url: str | None = getattr(settings, "http_proxy_url", None)
        root = getattr(
            settings,
            "perplexity_base_url",
            "https://api.perplexity.ai",
        ).rstrip("/")
        self._root_url: str = root
        # On docs perplexity, all Chat Compilations go to /v2
        # https://docs.perplexity.ai/docs/grounded-llm/openai-compatibility
        self._base_url: str = f"{root}/v2"
        # Model: use Sonar-pro (recommended in docks) default.
        # Claude Sonnet 4.5 is called by another client (Anthropic) rather than via Perplexity.
        self._model: str = getattr(
            settings,
            "perplexity_model",
            "sonar-pro",
        )
        if not self._api_key:
            raise RuntimeError('PERPLEXITY_API_KEY is not set in the environment.')

    async def search(
        self,
        query: str,
        *,
        system_prompt: str | None = None,
        keywords: list[str] | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Run a search through Perplexity and return the normalized results list.

        :param query: User request.
        :Param system_prompt: Additional system-prompt for model behaviour settings.
        :Param keywords: Keywords/List to focus search.
        :Paragraph max_results: Number of results desired (best-effort)).
        :Retorn: List of documents with field, url, snippet, score.
        """

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        # We're building a clue for a model that takes key words into account.
        keywords_text = ""
        if keywords:
            joined = ", ".join(sorted(set(k for k in keywords if k)))
            if joined:
                keywords_text = (
                    ' Focus on the following key themes and terms: ' + joined + "."
                )

        system = (
            system_prompt
            or (
                "You're an assistant for research on construction projects, tenders "
                'and companies. Select only relevant results and do not add fictional references.'
            )
        ) + keywords_text

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
            "max_tokens": 512,
            "temperature": 0.2,
            "search_mode": "web",
            "num_search_results": max_results,
            "return_images": False,
            "return_related_questions": False,
        }

        logger.info(
            "Perplexity search: model=%s results=%s query=%s",
            self._model,
            max_results,
            query,
        )
        async with httpx.AsyncClient(timeout=60.0, proxy=self._proxy_url) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            # If Perplexity returned a detailed error to JSON, add it to the exception message.
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # noqa: TRY301
                detail = ""
                try:
                    err_json = response.json()
                    detail = f" Details: {err_json}"
                except Exception:  # noqa: BLE001
                    detail = f" Body: {response.text}"
                raise httpx.HTTPStatusError(
                    f"Perplexity API error {response.status_code}.{detail}",
                    request=exc.request,
                    response=exc.response,
                ) from None
            data = response.json()

        results: list[dict[str, Any]] = []

        # Main source of documentation references: top-pel search_results.
        search_results = data.get("search_results") or []
        logger.info("Perplexity results: %s", len(search_results))
        for idx, item in enumerate(search_results):
            url = item.get("url") or ""
            title = item.get("title") or url
            snippet = item.get("snippet") or ""
            score = item.get("score")
            if score is None:
                score = max(0.0, 1.0 - idx * 0.05)
            results.append(
                {
                    "rank": idx + 1,
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "score": float(score),
                }
            )

        # If search_results is empty for some reason, let's try to pull out the text of the answer.
        if not results:
            choices = data.get("choices") or []
            if choices:
                first = choices[0] or {}
                message = first.get("message") or {}
                content = message.get("content") or ""
                results.append(
                    {
                        "rank": 1,
                        "title": 'Response Perplexity',
                        "url": "",
                        "snippet": content,
                        "score": 1.0,
                    }
                )

        return results[:max_results]

    async def search_web(
        self,
        query: str,
        *,
        max_results: int = 10,
        max_tokens: int | None = None,
        max_tokens_per_page: int | None = None,
        search_domain_filter: list[str] | None = None,
        search_language_filter: list[str] | None = None,
        search_recency_filter: str | None = None,
        search_after_date_filter: str | None = None,
        search_before_date_filter: str | None = None,
        country: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run a search through Perplexity Search API.

        :param query: Search request.
        :param max_results: Number of results.
        :param max_tokens: Total response current limit.
        :param max_tokens_per_page: Distillation of currents onto the page.
        :param search_domain_filter: Domain filter.
        :param search_language_filter: Language filter.
        :Param search_recency_filter: Freshness Window (hur/day/week/month/year)).
        :Paragraph search_after_date_filter: Start date of the window (YYYY-MM-DD)).
        :Paragraph search_before_date_filter: Date of window end (YYYY-MM-DD)).
        :param search_mode: Search mode (web/academic/sec).
        :param country: Geofilter (e.g. RU).
        :Retorn: List of documents with field, url, snippet, score.
        """

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        safe_max_results = max(1, min(20, max_results))
        payload: dict[str, Any] = {"query": query, "max_results": safe_max_results}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if max_tokens_per_page is not None:
            payload["max_tokens_per_page"] = max_tokens_per_page
        if search_domain_filter:
            payload["search_domain_filter"] = search_domain_filter
        if search_language_filter:
            payload["search_language_filter"] = search_language_filter
        if search_recency_filter:
            payload["search_recency_filter"] = search_recency_filter
        if search_after_date_filter:
            payload["search_after_date_filter"] = search_after_date_filter
        if search_before_date_filter:
            payload["search_before_date_filter"] = search_before_date_filter
        if country:
            payload["country"] = country

        logger.info(
            "Perplexity search_web: results=%s query=%s filters=%s",
            max_results,
            query,
            {k: v for k, v in payload.items() if k not in {"query"}},
        )
        async with httpx.AsyncClient(timeout=60.0, proxy=self._proxy_url) as client:
            response = await client.post(
                f"{self._root_url}/search",
                headers=headers,
                json=payload,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # noqa: TRY301
                detail = ""
                try:
                    err_json = response.json()
                    detail = f" Details: {err_json}"
                except Exception:  # noqa: BLE001
                    detail = f" Body: {response.text}"
                raise httpx.HTTPStatusError(
                    f"Perplexity Search API error {response.status_code}.{detail}",
                    request=exc.request,
                    response=exc.response,
                ) from None
            data = response.json()

        results: list[dict[str, Any]] = []
        for idx, item in enumerate(data.get("results") or []):
            url = item.get("url") or ""
            title = item.get("title") or url
            snippet = item.get("snippet") or ""
            results.append(
                {
                    "rank": idx + 1,
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "score": float(item.get("score") or max(0.0, 1.0 - idx * 0.05)),
                    "date": item.get("date"),
                    "last_updated": item.get("last_updated"),
                }
            )
        return results


__all__ = ["PerplexityClient"]

