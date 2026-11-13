"""Клиент для работы с Seldon Tenders API (заказы: New, Status, Result, Get).

Используется для получения актуальных данных об участниках — заказчиках и победителях
(не для участия в тендерах). Реальный API: https://apitorgi.myseldon.com — авторизация
User/Login (name, password), далее token в URL. Модель заказов: Purchases/New → Status →
Result (постранично). Ограничение: не более 1 запроса в секунду.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.core.config import get_settings
from app.services.http_client import HttpClient

logger = logging.getLogger(__name__)

# Интервал между запросами к Seldon (секунды)
SELDON_RATE_LIMIT_SEC = 1.0


class SeldonClient:
    """Клиент доступа к Seldon Tenders API (order-based)."""

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.seldon_base_url).rstrip("/")
        if not self._base_url:
            raise ValueError("SELDON_BASE_URL не задан")
        self._client = HttpClient()
        self._token: str | None = settings.seldon_api_key
        self._token_expires_at: datetime | None = None
        self._login = settings.seldon_login
        self._password = settings.seldon_password
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_at: float = 0.0

    async def _rate_limit(self) -> None:
        async with self._rate_limit_lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_at
            if elapsed < SELDON_RATE_LIMIT_SEC:
                await asyncio.sleep(SELDON_RATE_LIMIT_SEC - elapsed)
            self._last_request_at = asyncio.get_event_loop().time()

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _ensure_token(self) -> str:
        if self._token and self._token_expires_at and datetime.now(timezone.utc) < self._token_expires_at:
            return self._token
        if self._login and self._password:
            await self._rate_limit()
            url = self._url("User/Login")
            try:
                data = await self._client.post_json(url, json={"name": self._login, "password": self._password})
            except Exception as e:
                logger.exception("Seldon Login failed: %s", e)
                raise
            status = data.get("status") or {}
            if status.get("code") != 200:
                raise RuntimeError(f"Seldon Login error: {status.get('descr', data)}")
            result = data.get("result") or {}
            self._token = result.get("token")
            if not self._token:
                raise RuntimeError("Seldon Login: token not in response")
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=23)
            logger.info("Seldon token obtained, expires in 23h")
            return self._token
        if self._token:
            return self._token
        raise ValueError("Seldon: задайте seldon_login/seldon_password или seldon_api_key")

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        token = await self._ensure_token()
        await self._rate_limit()
        url = self._url(path)
        params = {"token": token}
        data = await self._client.post_json(url, params=params, json=body or {})
        status = data.get("status") or {}
        if status.get("code") == 401:
            self._token = None
            self._token_expires_at = None
            raise RuntimeError("Seldon token expired or invalid (401)")
        if status.get("code") not in (200, None):
            raise RuntimeError(f"Seldon API error {status.get('code')}: {status.get('descr', data)}")
        return data.get("result")

    async def get_filters(self) -> list[dict[str, Any]]:
        """Получить список поисковых фильтров учётной записи."""
        result = await self._post("User/Filters")
        if not result:
            return []
        filters = result.get("filters")
        return filters if isinstance(filters, list) else []

    async def create_order_purchases(
        self,
        filter_id: int,
        date_from: str,
        date_to: str,
        subtype: int | None = None,
    ) -> str:
        """Создать заказ на получение закупок. Возвращает taskId."""
        body: dict[str, Any] = {
            "filterId": filter_id,
            "dateFrom": date_from,
            "dateTo": date_to,
        }
        if subtype is not None:
            body["subtype"] = subtype
        result = await self._post("Purchases/New", body)
        task_id = result.get("taskId") if result else None
        if not task_id:
            raise RuntimeError("Seldon Purchases/New: taskId not in response")
        return str(task_id)

    async def create_order_protocols(
        self,
        filter_id: int,
        date_from: str,
        date_to: str,
        subtype: int | None = None,
    ) -> str:
        """Создать заказ на получение протоколов. Возвращает taskId."""
        body: dict[str, Any] = {
            "filterId": filter_id,
            "dateFrom": date_from,
            "dateTo": date_to,
        }
        if subtype is not None:
            body["subtype"] = subtype
        result = await self._post("Protocols/New", body)
        task_id = result.get("taskId") if result else None
        if not task_id:
            raise RuntimeError("Seldon Protocols/New: taskId not in response")
        return str(task_id)

    async def create_order_contracts(
        self,
        filter_id: int,
        date_from: str,
        date_to: str,
        subtype: int | None = None,
    ) -> str:
        """Создать заказ на получение контрактов. Возвращает taskId."""
        body: dict[str, Any] = {
            "filterId": filter_id,
            "dateFrom": date_from,
            "dateTo": date_to,
        }
        if subtype is not None:
            body["subtype"] = subtype
        result = await self._post("Contracts/New", body)
        task_id = result.get("taskId") if result else None
        if not task_id:
            raise RuntimeError("Seldon Contracts/New: taskId not in response")
        return str(task_id)

    async def get_order_status(self, task_id: str, content_type: str = "purchases") -> dict[str, Any]:
        """Проверить статус заказа. content_type: purchases | protocols | contracts."""
        path = f"{content_type.capitalize()}/Status"
        result = await self._post(path, {"taskId": task_id})
        return result or {}

    async def wait_order_ready(
        self,
        task_id: str,
        content_type: str = "purchases",
        poll_interval: float = 1.0,
        max_wait_sec: float = 600.0,
    ) -> None:
        """Ждать выполнения заказа. searchStatus.code: 1=wait, 2=in progress, 3=ready, 4=error."""
        path = f"{content_type.capitalize()}/Status"
        started = asyncio.get_event_loop().time()
        while True:
            result = await self._post(path, {"taskId": task_id})
            if result is None:
                await asyncio.sleep(poll_interval)
                if asyncio.get_event_loop().time() - started > max_wait_sec:
                    raise TimeoutError(f"Seldon order {task_id} not ready within {max_wait_sec}s")
                continue
            search_status = result.get("searchStatus") or {}
            code = search_status.get("code")
            if code == 3:
                return
            if code == 4:
                raise RuntimeError(f"Seldon order {task_id} error: {search_status.get('descr', result)}")
            if asyncio.get_event_loop().time() - started > max_wait_sec:
                raise TimeoutError(f"Seldon order {task_id} not ready within {max_wait_sec}s")
            await asyncio.sleep(poll_interval)

    async def get_purchases_result_page(self, task_id: str, page_index: int) -> list[dict[str, Any]]:
        """Получить одну страницу закупок (до 100 записей)."""
        result = await self._post("Purchases/Result", {"taskId": task_id, "pageIndex": page_index})
        if not result:
            return []
        purchases = result.get("purchases")
        return purchases if isinstance(purchases, list) else []

    async def get_purchases_result_all(self, task_id: str) -> list[dict[str, Any]]:
        """Обойти все страницы Result и вернуть все закупки."""
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            chunk = await self.get_purchases_result_page(task_id, page)
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
        return out

    async def get_purchase(self, seldon_id: int, report_id: int = 2) -> dict[str, Any] | None:
        """Получить одну закупку по seldonId и reportId."""
        result = await self._post("Purchases/Get", {"seldonId": seldon_id, "reportId": report_id, "etpId": None})
        if not result:
            return None
        purchases = result.get("purchases")
        if isinstance(purchases, list) and purchases:
            return purchases[0]
        if isinstance(result, dict) and "seldonId" in result:
            return result
        return None

    async def get_protocols_result_page(self, task_id: str, page_index: int) -> list[dict[str, Any]]:
        """Получить одну страницу протоколов."""
        result = await self._post("Protocols/Result", {"taskId": task_id, "pageIndex": page_index})
        if not result:
            return []
        protocols = result.get("protocols")
        return protocols if isinstance(protocols, list) else []

    async def get_protocols_result_all(self, task_id: str) -> list[dict[str, Any]]:
        """Обойти все страницы протоколов."""
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            chunk = await self.get_protocols_result_page(task_id, page)
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
        return out

    async def get_protocol_by_purchase(self, seldon_id: int, report_id: int = 2) -> dict[str, Any] | None:
        """Получить протокол по закупке (Protocols/Get)."""
        result = await self._post("Protocols/Get", {"seldonId": seldon_id, "reportId": report_id, "etpId": None})
        if not result:
            return None
        protocols = result.get("protocols")
        if isinstance(protocols, list) and protocols:
            return protocols[0]
        if isinstance(result, dict) and "seldonId" in result:
            return result
        return None

    async def get_contracts_result_page(self, task_id: str, page_index: int) -> list[dict[str, Any]]:
        """Получить одну страницу контрактов."""
        result = await self._post("Contracts/Result", {"taskId": task_id, "pageIndex": page_index})
        if not result:
            return []
        contracts = result.get("contracts")
        return contracts if isinstance(contracts, list) else []

    async def get_contracts_result_all(self, task_id: str) -> list[dict[str, Any]]:
        """Обойти все страницы контрактов."""
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            chunk = await self.get_contracts_result_page(task_id, page)
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
        return out

    async def get_contract_by_purchase(self, seldon_id: int, report_id: int = 2) -> dict[str, Any] | None:
        """Получить контракт по закупке (Contracts/Get). Документация уточняет входные параметры."""
        result = await self._post("Contracts/Get", {"seldonId": seldon_id, "reportId": report_id, "etpId": None})
        if not result:
            return None
        contracts = result.get("contracts")
        if isinstance(contracts, list) and contracts:
            return contracts[0]
        if isinstance(result, dict) and "seldonId" in result:
            return result
        return None
