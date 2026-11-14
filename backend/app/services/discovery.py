"""Auto search for sources by key words.

Author: Maxi-online
"""

from __future__ import annotations

from typing import Any
import json
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse, urlunparse

from app.core.config import get_settings
from app.services.http_client import HttpClient
from app.services.perplexity_client import PerplexityClient
from app.services.openai_client import OpenAIClient


class DiscoveryService:
    """Auto source detection service.

    :Param search_url: URL search API with template {query}.
    :param api_key: API search key.
    """

    def __init__(self, search_url: str | None = None, api_key: str | None = None) -> None:
        settings = get_settings()
        self._search_url = search_url or settings.discovery_search_url
        self._api_key = api_key or settings.discovery_api_key
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        self._client = HttpClient(headers=headers)
        self._perplexity_available = bool(getattr(settings, "perplexity_api_key", None))

    async def search_sources(self, query: str, *, max_results: int = 1000) -> list[dict[str, Any]]:
        """To search for sources by the key word.

        :param query: Search request.
        :return: List of results found.
        """

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        # (1) Perplexity: LLM extended request + web search for sources
        if self._perplexity_available:
            try:
                perplexity = PerplexityClient()
                p_query = await self._expand_query_llm(query)
                p_results = await perplexity.search_web(
                    p_query,
                    max_results=max_results,
                    search_language_filter=["ru"],
                    country="RU",
                    search_recency_filter="year",
                )
                for item in p_results:
                    url = item.get("url") or ""
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    results.append(
                        {
                            "title": item.get("title") or url,
                            "url": url,
                        }
                    )
            except Exception:
                # We don't break the discovery if Perplexity is temporarily unavailable.
                pass

        # (2) SerpaPI (DISCOVERY_SEARCH_URL) is a standard search for Google News
        if self._search_url:
            url = self._build_url(query)
            data = await self._client.get_json(url)
            if isinstance(data, dict):
                if "error" in data:
                    # If SerpAPI returns an error, we just miss its results.
                    pass
                else:
                    if "news_results" in data:
                        for item in data.get("news_results", []):
                            link = item.get("link") or item.get("source_link") or ""
                            if not link or link in seen_urls:
                                continue
                            seen_urls.add(link)
                            results.append(
                                {
                                    "title": item.get("title") or item.get("source") or link,
                                    "url": link,
                                }
                            )
                    if "organic_results" in data:
                        for item in data.get("organic_results", []):
                            link = item.get("link") or ""
                            if not link or link in seen_urls:
                                continue
                            seen_urls.add(link)
                            results.append(
                                {
                                    "title": item.get("title") or link,
                                    "url": link,
                                }
                            )
                    for item in data.get("items", []):
                        link = item.get("link") or ""
                        if not link or link in seen_urls:
                            continue
                        seen_urls.add(link)
                        results.append(
                            {
                                "title": item.get("title") or link,
                                "url": link,
                            }
                        )
            elif isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    link = item.get("link") or item.get("url") or ""
                    if not link or link in seen_urls:
                        continue
                    seen_urls.add(link)
                    results.append(
                        {
                            "title": item.get("title") or link,
                            "url": link,
                        }
                    )

        if not results and not self._perplexity_available and not self._search_url:
            raise ValueError('DISCOVERY_SEARCH_URL not specified and Perplexity not available')

        return results

    async def _expand_query_llm(self, query: str) -> str:
        client = OpenAIClient()
        system = (
            'ATTENTION: How to improve the request for as accurate a search as possible. '
            'The aim is to find sources where information on tenders and construction projects in the Russian Federation is published: '
            'Specialists, media, tender and procurement portals (not just links to main pages), '
            'However, it is not possible for the Committee to decide on the scope of its work (i.e., but also sections with articles/news/publications). '
            "Add a role (contractor/contractor/contractors), the words 'MI/journal/portal/tenders/purchases', "
            'Russia/FR, delete Kazakhstan. Request for Russian, non-bullet operators and quotations. '
            'Give it back to JSON, the object of the type {"query": "..."}.'
        )
        user_content = (
            'The phrase:\n'
            f"{query}\n\n"
            'Return JSON – object {"query": "..."}.'
        )
        try:
            response = await client.chat(
                system,
                [{"role": "user", "content": user_content}],
            )
            content = response.get("content") or []
            text_blocks = [b.get("text") for b in content if b.get("type") == "text"]
            merged = "\n".join(t for t in text_blocks if t)
            data = json.loads(merged)
            expanded = str(data.get("query") or "").strip()
            return expanded or query
        except Exception:
            return query

    def _build_url(self, query: str) -> str:
        """Set up an uRL search to take into account the access key.

        :param query: Search request.
        :return: Full URL request.
        """

        if not self._search_url:
            raise ValueError('DISCOVERY_SEARCH_URL not specified')
        safe_query = quote_plus(query)
        if "{query}" in self._search_url or "{api_key}" in self._search_url:
            safe_key = quote_plus(self._api_key) if self._api_key else ""
            return self._search_url.format(query=safe_query, api_key=safe_key)
        parsed = urlparse(self._search_url)
        if not parsed.scheme:
            raise ValueError('DISCOVERY_SEARCH_URL should start at http://https')
        params = parse_qs(parsed.query)
        if "q" not in params:
            params["q"] = [query]
        if self._api_key and "api_key" not in params:
            params["api_key"] = [self._api_key]
        new_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
