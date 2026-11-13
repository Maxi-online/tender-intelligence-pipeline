"""Клиент Dadata для обогащения данных о компаниях.

Используются методы:
- findById/party (поиск организации по ИНН/ОГРН)
- findByEmail/company (поиск компании по корпоративному email)
- findAffiliated/party (поиск аффилированных компаний по ИНН учредителя/руководителя)

Документация:
- https://dadata.ru/api/find-party/
- https://dadata.ru/api/find-company/by-email/
- https://dadata.ru/api/find-affiliated/
"""

from __future__ import annotations

from typing import Any

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DadataClient:
    """Простой HTTP-клиент для REST API Dadata."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str | None = settings.dadata_api_key
        self._secret_key: str | None = settings.dadata_secret_key
        self._base_url: str = "https://suggestions.dadata.ru/suggestions/api/4_1/rs"
        if not self._api_key:
            raise RuntimeError("DADATA_API_KEY не задан в окружении.")

    def _auth_headers(self, with_secret: bool = False) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {self._api_key}",
        }
        if with_secret and self._secret_key:
            headers["X-Secret"] = self._secret_key
        return headers

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        with_secret: bool = False,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        logger.info("Dadata request: path=%s payload=%s", path, payload)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self._auth_headers(with_secret=with_secret),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "Dadata response: path=%s suggestions=%s",
                path,
                len((data or {}).get("suggestions") or []),
            )
            return data

    async def find_party_by_inn_ogrn(
        self,
        query: str,
        *,
        count: int = 10,
        kpp: str | None = None,
        branch_type: str | None = None,
        type: str | None = None,
        status: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Поиск организации по ИНН/ОГРН.

        Возвращает массив объектов из поля suggestions.
        """

        payload: dict[str, Any] = {"query": query, "count": count}
        if kpp:
            payload["kpp"] = kpp
        if branch_type:
            payload["branch_type"] = branch_type
        if type:
            payload["type"] = type
        if status:
            payload["status"] = status
        data = await self._post("findById/party", payload)
        return data.get("suggestions") or []

    async def find_company_by_email(self, email: str) -> list[dict[str, Any]]:
        """Поиск компании по корпоративному email.

        Требует API-ключ и секретный ключ.
        """

        data = await self._post(
            "findByEmail/company",
            {"query": email},
            with_secret=True,
        )
        return data.get("suggestions") or []

    async def find_affiliated(
        self,
        inn_person_or_org: str,
        *,
        count: int = 50,
        scope: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Поиск аффилированных компаний по ИНН учредителя/руководителя."""

        payload: dict[str, Any] = {"query": inn_person_or_org, "count": count}
        if scope:
            payload["scope"] = scope
        data = await self._post("findAffiliated/party", payload)
        return data.get("suggestions") or []

    async def suggest_party(
        self,
        query: str,
        *,
        count: int = 10,
        status: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Поиск организации по названию (suggest/party)."""
        payload: dict[str, Any] = {"query": query, "count": count}
        if status:
            payload["status"] = status
        data = await self._post("suggest/party", payload)
        return data.get("suggestions") or []


def _normalize_dadata_party(party: dict[str, Any]) -> dict[str, Any]:
    """Нормализовать карточку организации Dadata в общий формат CompanyProfile-like."""

    data = party.get("data") or {}
    address = (data.get("address") or {}).get("value")
    phones = [(p.get("value") or "") for p in (data.get("phones") or []) if p.get("value")]
    emails = [(e.get("value") or "") for e in (data.get("emails") or []) if e.get("value")]
    opf = data.get("opf") or {}
    name = data.get("name") or {}
    management = data.get("management") or {}
    state = data.get("state") or {}

    return {
        "source": "dadata_party",
        "inn": data.get("inn"),
        "ogrn": data.get("ogrn"),
        "kpp": data.get("kpp"),
        "name": name.get("full_with_opf") or party.get("value"),
        "short_name": name.get("short_with_opf") or name.get("short"),
        "opf_full": opf.get("full"),
        "opf_short": opf.get("short"),
        "okved": data.get("okved"),
        "okved_name": None,
        "address": address,
        "phones": phones,
        "emails": emails,
        "management_name": management.get("name"),
        "management_post": management.get("post"),
        "status": state.get("status"),
    }


def _normalize_dadata_email_company(item: dict[str, Any]) -> dict[str, Any]:
    """Нормализовать ответ findByEmail/company в общий формат."""

    data = item.get("data") or {}
    company = data.get("company") or {}
    email = data.get("email") or {}
    return {
        "source": "dadata_email_company",
        "email": email.get("source") or item.get("value"),
        "domain": company.get("domain"),
        "name": company.get("name"),
        "inn": company.get("inn"),
        "ogrn": company.get("ogrn"),
        "okved": company.get("okved"),
        "okved_name": company.get("okved_name"),
        "employee_count": company.get("employee_count"),
        "income": company.get("income"),
        "city": company.get("city"),
        "timezone": company.get("timezone"),
    }


__all__ = [
    "DadataClient",
    "_normalize_dadata_party",
    "_normalize_dadata_email_company",
]

