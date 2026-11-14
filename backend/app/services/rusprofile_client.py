"""Rusprofile client to search for company information.

Rusprofile doesn't have an official open API, so it's implemented here
Minimum HTTP client with ability to connect documented API
Or a proxie wrapper if she shows up.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.services.http_client import HttpClient


class RusprofileClient:
    """The client is looking for companies on rusprofile.ru.

    Two regimes are maintained:
    - If RUSPROFILE_BASE_URL is given and returned JSON format {"results": [...]}
      (own Proxi/API) is used.
    - Otherwise, the HTML parking of the public site https://www.rusprofile.ru is performed.
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
        "Searching through the external JSON API-proxi, if he's in the mood."

        if not self._api_base:
            return []
        from urllib.parse import urlencode
        base = self._api_base.rstrip("/")
        # Say the proxie takes q and limit as quaerry parameters.
        params = {"q": query, "limit": str(limit)}
        url = f"{base}?{urlencode(params)}"
        data = await self._http.get_json(url)
        return data.get("results") or []

    async def _search_via_html(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        'HTML parsing rusprofile.ru/search.'

        from urllib.parse import urlencode

        base = "https://www.rusprofile.ru/search"
        url = f"{base}?{urlencode({'query': query})}"
        html = await self._http.get_text(url)
        soup = BeautifulSoup(html, "lxml")

        results: list[dict[str, Any]] = []

        # Main scenario: company cards on the search list.
        # The site structure can change, so we use a few heuristics.
        cards = soup.select("div.company-item") or soup.select("article.company-item")
        if not cards:
            # fallback: any references to /id/<number> as company cards
            links = soup.select("a[href^='/id/']")
            for link in links[:limit]:
                name = link.get_text(strip=True)
                href = link.get("href") or ""
                full_url = f"https://www.rusprofile.ru{href}"
                # We're looking for text around the link to pull out the DIN/DOE and address
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
        'Search for IDN/name/email/phone on Rusprofile.'

        # If the external JSON-proxie is set, we use it.
        if self._api_base:
            try:
                api_results = await self._search_via_api(query, limit)
                if api_results:
                    return api_results[:limit]
            except Exception:  # noqa: BLE001
                # We're gonna go back to HTML parsing.
                pass

        return await self._search_via_html(query, limit)


__all__ = ["RusprofileClient"]

