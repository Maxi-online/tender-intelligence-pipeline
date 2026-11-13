"""Клиент Rusprofile для поиска информации о компании.

У Rusprofile нет официального открытого API, поэтому здесь реализован
минимальный HTTP-клиент с возможностью подключить документированный API
или прокси-обёртку, если она появится.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.services.http_client import HttpClient


class RusprofileClient:
    """Клиент для поиска компаний на rusprofile.ru.

    Поддерживаются два режима:
    - Если RUSPROFILE_BASE_URL задан и возвращает JSON формата {"results": [...]}
      (собственный прокси/API) — используется он.
    - В противном случае выполняется HTML-парсинг публичного сайта https://www.rusprofile.ru.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._api_base: str | None = settings.rusprofile_base_url or None
        self._http = HttpClient(timeout=30.0)

    async def _search_via_api(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Поиск через внешний JSON API-прокси, если он настроен."""

        if not self._api_base:
            return []
        from urllib.parse import urlencode
        base = self._api_base.rstrip("/")
        # Допустим, прокси принимает q и limit как query-параметры.
        params = {"q": query, "limit": str(limit)}
        url = f"{base}?{urlencode(params)}"
        data = await self._http.get_json(url)
        return data.get("results") or []

    async def _search_via_html(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """HTML-парсинг rusprofile.ru/search."""

        from urllib.parse import urlencode

        base = "https://www.rusprofile.ru/search"
        url = f"{base}?{urlencode({'query': query})}"
        html = await self._http.get_text(url)
        soup = BeautifulSoup(html, "lxml")

        results: list[dict[str, Any]] = []

        # Основной сценарий: карточки компаний в списке поиска.
        # Структура сайта может меняться, поэтому используем несколько эвристик.
        cards = soup.select("div.company-item") or soup.select("article.company-item")
        if not cards:
            # fallback: любые ссылки на /id/<число> как карточки компаний
            links = soup.select("a[href^='/id/']")
            for link in links[:limit]:
                name = link.get_text(strip=True)
                href = link.get("href") or ""
                full_url = f"https://www.rusprofile.ru{href}"
                # Ищем текст вокруг ссылки, чтобы вытащить ИНН/ОГРН и адрес
                container = link.find_parent("div") or link.parent
                text_block = container.get_text(" ", strip=True) if container else ""
                inn = None
                ogrn = None
                address = None
                import re

                inn_match = re.search(r"ИНН[:\s]+(\d{10,12})", text_block)
                ogrn_match = re.search(r"ОГРН[:\s]+(\d{13})", text_block)
                addr_match = re.search(r"Адрес[:\s]+(.+)", text_block)
                if inn_match:
                    inn = inn_match.group(1)
                if ogrn_match:
                    ogrn = ogrn_match.group(1)
                if addr_match:
                    address = addr_match.group(1).strip()
                results.append(
                    {
                        "source": "rusprofile_html",
                        "name": name or None,
                        "inn": inn,
                        "ogrn": ogrn,
                        "address": address,
                        "url": full_url,
                    }
                )
            return results[:limit]

        import re

        for card in cards[:limit]:
            link = card.select_one("a[href^='/id/']")
            if not link:
                link = card.find("a")
            if not link:
                continue
            name = link.get_text(strip=True)
            href = link.get("href") or ""
            full_url = f"https://www.rusprofile.ru{href}"
            text_block = card.get_text(" ", strip=True)
            inn = None
            ogrn = None
            address = None
            inn_match = re.search(r"ИНН[:\s]+(\d{10,12})", text_block)
            ogrn_match = re.search(r"ОГРН[:\s]+(\d{13})", text_block)
            addr_match = re.search(r"Адрес[:\s]+(.+)", text_block)
            if inn_match:
                inn = inn_match.group(1)
            if ogrn_match:
                ogrn = ogrn_match.group(1)
            if addr_match:
                address = addr_match.group(1).strip()
            results.append(
                {
                    "source": "rusprofile_html",
                    "name": name or None,
                    "inn": inn,
                    "ogrn": ogrn,
                    "address": address,
                    "url": full_url,
                }
            )
        return results

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Поиск компании по ИНН/названию/email/телефону на Rusprofile."""

        # Если настроен внешний JSON-прокси — используем его.
        if self._api_base:
            try:
                api_results = await self._search_via_api(query, limit)
                if api_results:
                    return api_results[:limit]
            except Exception:  # noqa: BLE001
                # Падаем обратно на HTML-парсинг.
                pass

        return await self._search_via_html(query, limit)


__all__ = ["RusprofileClient"]

