"""Автопоиск источников по ключевым словам.

Автор: Maxi-online
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
    """Сервис автообнаружения источников.

    :param search_url: URL поискового API с шаблоном {query}.
    :param api_key: Ключ для поискового API.
    """

    def __init__(self, search_url: str | None = None, api_key: str | None = None) -> None:
        settings = get_settings()
        self._search_url = search_url or settings.discovery_search_url
        self._api_key = api_key or settings.discovery_api_key
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        self._client = HttpClient(headers=headers)
        self._perplexity_available = bool(getattr(settings, "perplexity_api_key", None))

    async def search_sources(self, query: str, *, max_results: int = 1000) -> list[dict[str, Any]]:
        """Выполнить поиск источников по ключевому слову.

        :param query: Поисковый запрос.
        :return: Список найденных результатов.
        """

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        # 1) Perplexity: LLM-расширенный запрос + web-поиск источников
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
                # Не ломаем discovery, если Perplexity временно недоступен.
                pass

        # 2) SerpAPI (DISCOVERY_SEARCH_URL) — стандартный поиск Google News
        if self._search_url:
            url = self._build_url(query)
            data = await self._client.get_json(url)
            if isinstance(data, dict):
                if "error" in data:
                    # Если SerpAPI вернул ошибку, просто пропускаем его результаты.
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
            raise ValueError("DISCOVERY_SEARCH_URL не задан и Perplexity недоступен")

        return results

    async def _expand_query_llm(self, query: str) -> str:
        client = OpenAIClient()
        system = (
            "ВНИМАТЕЛЬНО ПРОАНАЛИЗИРУЙ, как улучшить запрос для максимально точного поиска. "
            "Цель — находить источники, где публикуют информацию о тендерах и строительных проектах в РФ: "
            "спецжурналы, СМИ, порталы по тендерам и закупкам (не только ссылки на главные страницы, "
            "но и разделы со статьями/новостями/объявлениями). "
            "Добавь роли (заказчик/подрядчик/контакты), слова 'СМИ/журнал/портал/тендеры/закупки', "
            "Россия/РФ, исключи Казахстан. Запрос на русском, без булевых операторов и кавычек. "
            "Верни ТОЛЬКО JSON‑объект вида {\"query\": \"...\"}."
        )
        user_content = (
            "Фраза:\n"
            f"{query}\n\n"
            "Верни JSON‑объект {\"query\": \"...\"}."
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
        """Сформировать URL поиска с учетом ключа доступа.

        :param query: Поисковый запрос.
        :return: Полный URL запроса.
        """

        if not self._search_url:
            raise ValueError("DISCOVERY_SEARCH_URL не задан")
        safe_query = quote_plus(query)
        if "{query}" in self._search_url or "{api_key}" in self._search_url:
            safe_key = quote_plus(self._api_key) if self._api_key else ""
            return self._search_url.format(query=safe_query, api_key=safe_key)
        parsed = urlparse(self._search_url)
        if not parsed.scheme:
            raise ValueError("DISCOVERY_SEARCH_URL должен начинаться с http/https")
        params = parse_qs(parsed.query)
        if "q" not in params:
            params["q"] = [query]
        if self._api_key and "api_key" not in params:
            params["api_key"] = [self._api_key]
        new_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
