"""HTTP is a client for access to external sources.

Author: Maxi-online
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from app.core.config import get_settings

class HttpClient:
    """Asynchronous HTTP client with basic error processing.

    :param timeout: Timeout request in seconds.
    :param heders: default headings for all queries.
    """

    def __init__(self, timeout: float = 30.0, headers: dict[str, str] | None = None) -> None:
        settings = get_settings()
        self._timeout = timeout
        base_headers = {"User-Agent": settings.user_agent}
        base_headers.update(headers or {})
        self._headers = base_headers
        self._proxy_url = settings.http_proxy_url or None
        self._delay_min = settings.request_delay_min
        self._delay_max = settings.request_delay_max

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Do GET request and return JSON.

        :param url: Full URL request.
        :param pars:Query &apos; s request parameters.
        :return: Dissolved JSON response.
        """

        await asyncio.sleep(random.uniform(self._delay_min, self._delay_max))
        async with httpx.AsyncClient(
            timeout=self._timeout, headers=self._headers, proxy=self._proxy_url
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def post_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Do POST request and return JSON.

        :param url: Full URL request.
        :param pars:Query &apos; s request parameters.
        :param json: Query Body (JSON).
        :return: Dissolved JSON response.
        """

        await asyncio.sleep(random.uniform(self._delay_min, self._delay_max))
        async with httpx.AsyncClient(
            timeout=self._timeout, headers=self._headers, proxy=self._proxy_url
        ) as client:
            response = await client.post(url, params=params, json=json)
            response.raise_for_status()
            return response.json()

    async def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Do the GET request and return the text.

        :param url: Full URL request.
        :param pars:Query &apos; s request parameters.
        :return: Text of the reply.
        """

        await asyncio.sleep(random.uniform(self._delay_min, self._delay_max))
        async with httpx.AsyncClient(
            timeout=self._timeout, headers=self._headers, proxy=self._proxy_url
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.text

    async def get_bytes(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        """Do the GET request and return the bytes.

        :param url: Full URL request.
        :param pars:Query &apos; s request parameters.
        Byte content of the answer.
        """

        await asyncio.sleep(random.uniform(self._delay_min, self._delay_max))
        async with httpx.AsyncClient(
            timeout=self._timeout, headers=self._headers, proxy=self._proxy_url
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.content
