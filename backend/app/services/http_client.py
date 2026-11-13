"""HTTP клиент для доступа к внешним источникам.

Автор: Maxi-online
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from app.core.config import get_settings

class HttpClient:
    """Асинхронный HTTP клиент с базовой обработкой ошибок.

    :param timeout: Таймаут запроса в секундах.
    :param headers: Заголовки по умолчанию для всех запросов.
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
        """Выполнить GET запрос и вернуть JSON.

        :param url: Полный URL запроса.
        :param params: Query параметры запроса.
        :return: Распарсенный JSON-ответ.
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
        """Выполнить POST запрос и вернуть JSON.

        :param url: Полный URL запроса.
        :param params: Query параметры запроса.
        :param json: Тело запроса (JSON).
        :return: Распарсенный JSON-ответ.
        """

        await asyncio.sleep(random.uniform(self._delay_min, self._delay_max))
        async with httpx.AsyncClient(
            timeout=self._timeout, headers=self._headers, proxy=self._proxy_url
        ) as client:
            response = await client.post(url, params=params, json=json)
            response.raise_for_status()
            return response.json()

    async def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Выполнить GET запрос и вернуть текст.

        :param url: Полный URL запроса.
        :param params: Query параметры запроса.
        :return: Текст ответа.
        """

        await asyncio.sleep(random.uniform(self._delay_min, self._delay_max))
        async with httpx.AsyncClient(
            timeout=self._timeout, headers=self._headers, proxy=self._proxy_url
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.text

    async def get_bytes(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        """Выполнить GET запрос и вернуть байты.

        :param url: Полный URL запроса.
        :param params: Query параметры запроса.
        :return: Байтовое содержимое ответа.
        """

        await asyncio.sleep(random.uniform(self._delay_min, self._delay_max))
        async with httpx.AsyncClient(
            timeout=self._timeout, headers=self._headers, proxy=self._proxy_url
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.content
