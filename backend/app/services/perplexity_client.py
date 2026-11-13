"""Клиент Perplexity API для текстового/web-поиска.

В системе Perplexity используется для:
- Поиска информации о проектах, тендерах и госзаказах (ingest_perplexity_leads): по ключевым словам
  и запросам типа «госзакупки 44-ФЗ 223-ФЗ» находит ссылки на статьи/страницы, по ним парсим и пишем в БД.
- Автопоиска источников (DiscoveryService): поиск новых RSS/порталов по ключевым словам.
- Пользовательского поиска (semantic_search): первичный сбор результатов, затем ранжирование Claude.
- Обогащения компаний: поиск данных о компаниях (Rusprofile и др.).

Автор: Maxi-online (адаптация под LLM-поиск).
"""

from __future__ import annotations

from typing import Any

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class PerplexityClient:
    """Клиент Perplexity Chat Completions API.

    ВАЖНО: Perplexity всегда использует СВОИ модели (семейство Sonar).
    Claude в Perplexity запускать нельзя — для Claude Sonnet 4.5
    у нас отдельный клиент Anthropic (`ClaudeClient`).
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
        # По docs Perplexity все Chat Completions ходят на /v2
        # https://docs.perplexity.ai/docs/grounded-llm/openai-compatibility
        self._base_url: str = f"{root}/v2"
        # Модель: используем sonar-pro (рекомендуемую в доках) по умолчанию.
        # Claude Sonnet 4.5 вызывается ДРУГИМ клиентом (Anthropic), а не через Perplexity.
        self._model: str = getattr(
            settings,
            "perplexity_model",
            "sonar-pro",
        )
        if not self._api_key:
            raise RuntimeError("PERPLEXITY_API_KEY не задан в окружении.")

    async def search(
        self,
        query: str,
        *,
        system_prompt: str | None = None,
        keywords: list[str] | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Выполнить поиск через Perplexity и вернуть нормализованный список результатов.

        :param query: Пользовательский запрос.
        :param system_prompt: Дополнительный system-промпт для настройки поведения модели.
        :param keywords: Список ключевых слов/фраз для фокусировки поиска.
        :param max_results: Желаемое число результатов (best-effort).
        :return: Список документов с полями title, url, snippet, score.
        """

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        # Строим подсказку для модели с учётом ключевых слов.
        keywords_text = ""
        if keywords:
            joined = ", ".join(sorted(set(k for k in keywords if k)))
            if joined:
                keywords_text = (
                    " Фокусируйся на следующих ключевых темах и терминах: " + joined + "."
                )

        system = (
            system_prompt
            or (
                "Ты помощник для поиска информации по строительным проектам, тендерам "
                "и компаниям. Отбирай только релевантные результаты и не добавляй выдуманных ссылок."
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
            # Если Perplexity вернул подробную ошибку в JSON — добавим её в сообщение исключения.
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

        # Основной источник ссылок по документации: top-level search_results.
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

        # Если по какой-то причине search_results пуст, пробуем вытащить хотя бы текст ответа.
        if not results:
            choices = data.get("choices") or []
            if choices:
                first = choices[0] or {}
                message = first.get("message") or {}
                content = message.get("content") or ""
                results.append(
                    {
                        "rank": 1,
                        "title": "Ответ Perplexity",
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
        """Выполнить поиск через Perplexity Search API.

        :param query: Поисковый запрос.
        :param max_results: Количество результатов.
        :param max_tokens: Общий лимит токенов ответа.
        :param max_tokens_per_page: Лимит токенов на страницу.
        :param search_domain_filter: Фильтр доменов.
        :param search_language_filter: Фильтр языков.
        :param search_recency_filter: Окно свежести (hour/day/week/month/year).
        :param search_after_date_filter: Дата начала окна (YYYY-MM-DD).
        :param search_before_date_filter: Дата конца окна (YYYY-MM-DD).
        :param search_mode: Режим поиска (web/academic/sec).
        :param country: Геофильтр (например, RU).
        :return: Список документов с полями title, url, snippet, score.
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

