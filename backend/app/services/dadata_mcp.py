"""Dadata через OpenAI Responses API + MCP (одна точка настроек: gpt-5-nano, прокси).

По документации https://dadata.ru/mcp/:
- server_url: https://mcp.dadata.ru/mcp
- Авторизация: в headers передаётся authorization: "Bearer ${API_KEY}:${SECRET_KEY}"
- OpenAI при вызове MCP передаёт токен на сервер Dadata; 424 = OpenAI не смог получить
  список инструментов с сервера (таймаут, сеть или ответ сервера).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.openai_client import _load_openai_settings

logger = logging.getLogger(__name__)

DADATA_MCP_SERVER_URL = "https://mcp.dadata.ru/mcp"

# MCP Streamable HTTP: клиент шлёт JSON-RPC (initialize, затем tools/list).
# Dadata может поддерживать 2024-11-05 или 2025-03-26 — при 400 пробуем другую версию.
MCP_PROTOCOL_VERSION = "2024-11-05"


def _parse_mcp_response(resp: httpx.Response) -> dict | None:
    """Разобрать ответ MCP: либо application/json, либо SSE (event/data: {...})."""
    text = resp.text or ""
    if not text.strip():
        return None
    # Попытка как JSON
    if resp.headers.get("content-type", "").startswith("application/json"):
        try:
            return resp.json()
        except json.JSONDecodeError:
            pass
    # SSE: строки "data: {...}" — склеиваем все data и парсим
    data_parts = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("data:"):
            data_parts.append(s[5:].strip())
    if data_parts:
        payload = "\n".join(data_parts)
        if payload and payload != "[DONE]":
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                pass
    try:
        return resp.json()
    except json.JSONDecodeError:
        pass
    return None


def _get_dadata_credentials() -> tuple[str | None, str | None]:
    """Ключи Dadata: сначала из settings.json (как и OpenAI), затем из env через get_settings()."""
    settings = get_settings()
    try:
        cfg = _load_openai_settings(settings.openai_settings_path)
        api_key = cfg.get("dadata_api_key") or settings.dadata_api_key
        secret_key = cfg.get("dadata_secret_key") or settings.dadata_secret_key
        return (api_key or None, secret_key or None)
    except Exception:
        return (settings.dadata_api_key, settings.dadata_secret_key)


async def check_dadata_mcp_server() -> dict[str, Any]:
    """Проверить доступность MCP-сервера Dadata напрямую (без OpenAI).

    Отправляет initialize и tools/list по спецификации MCP Streamable HTTP.
    Успех: сервер отвечает и возвращает список инструментов.
    Ключи берутся из settings.json или env (как и для enrich_company_with_mcp).
    :return: {"ok": bool, "message": str, "tools_count": int | None, "error": str | None}
    """
    dadata_api_key, dadata_secret_key = _get_dadata_credentials()
    if not dadata_api_key or not dadata_secret_key:
        return {
            "ok": False,
            "message": "Задайте dadata_api_key и dadata_secret_key в config/settings.json или DADATA_API_KEY и DADATA_SECRET_KEY в env",
            "tools_count": None,
            "error": None,
        }
    auth_header = f"Bearer {dadata_api_key}:{dadata_secret_key}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": auth_header,
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }
    # Initialize (JSON-RPC)
    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "tpis-check", "version": "1.0"},
        },
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                DADATA_MCP_SERVER_URL,
                headers=headers,
                json=init_body,
            )
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "message": f"MCP initialize: HTTP {resp.status_code}",
                    "tools_count": None,
                    "error": resp.text[:500] if resp.text else None,
                }
            data = _parse_mcp_response(resp)
            if data is None:
                return {
                    "ok": False,
                    "message": "MCP initialize: не удалось разобрать ответ",
                    "tools_count": None,
                    "error": (resp.text or "")[:500],
                }
            if "result" not in data and "error" in data:
                return {
                    "ok": False,
                    "message": "MCP initialize: ошибка от сервера",
                    "tools_count": None,
                    "error": str(data.get("error")),
                }
            # tools/list
            list_body = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
            }
            resp2 = await client.post(
                DADATA_MCP_SERVER_URL,
                headers=headers,
                json=list_body,
            )
            if resp2.status_code != 200:
                return {
                    "ok": False,
                    "message": f"MCP tools/list: HTTP {resp2.status_code}",
                    "tools_count": None,
                    "error": resp2.text[:500] if resp2.text else None,
                }
            data2 = _parse_mcp_response(resp2)
            if data2 is None:
                return {
                    "ok": False,
                    "message": "MCP tools/list: не удалось разобрать ответ",
                    "tools_count": None,
                    "error": (resp2.text or "")[:500],
                }
            if "error" in data2:
                return {
                    "ok": False,
                    "message": "MCP tools/list: ошибка от сервера",
                    "tools_count": None,
                    "error": str(data2.get("error")),
                }
            tools = data2.get("result", {}).get("tools") or []
            return {
                "ok": True,
                "message": "MCP-сервер Dadata доступен, список инструментов получен",
                "tools_count": len(tools),
                "error": None,
            }
    except httpx.TimeoutException as e:
        return {
            "ok": False,
            "message": "Таймаут при обращении к MCP Dadata",
            "tools_count": None,
            "error": str(e),
        }
    except Exception as e:
        return {
            "ok": False,
            "message": "Ошибка при проверке MCP Dadata",
            "tools_count": None,
            "error": str(e),
        }


async def enrich_company_with_mcp(query: str) -> dict[str, Any] | None:
    """Получить данные о компании по ИНН/ОГРН через Dadata MCP по документации.

    Используется OpenAI Responses API с инструментом type=mcp (server_url Dadata).
    Модель сама вызывает MCP Dadata; результат берётся из output mcp_call.
    Ключи Dadata берутся из того же settings.json, что и OpenAI, с fallback на env.
    """
    settings = get_settings()
    dadata_api_key, dadata_secret_key = _get_dadata_credentials()
    if not dadata_api_key or not dadata_secret_key:
        logger.warning(
            "Dadata MCP skipped: задайте dadata_api_key и dadata_secret_key в config/settings.json или DADATA_* в env"
        )
        return None
    if not settings.http_proxy_url:
        logger.warning("Dadata MCP skipped: HTTP_PROXY_URL обязателен для OpenAI")
        return None

    try:
        openai_cfg = _load_openai_settings(settings.openai_settings_path)
    except Exception as e:
        logger.warning("Dadata MCP skipped: could not load OpenAI settings: %s", e)
        return None

    model = settings.openai_model or openai_cfg.get("model") or "gpt-5-nano"
    # Dadata: "Bearer ${API_KEY}:${SECRET_KEY}" — см. https://dadata.ru/mcp/
    dadata_token = f"Bearer {dadata_api_key}:{dadata_secret_key}"

    # По документации Dadata https://dadata.ru/mcp/ передаётся "headers": {"authorization": "Bearer KEY:SECRET"}.
    # OpenAI передаёт эти заголовки при вызове tools/list и вызовах инструментов на MCP-сервере.
    body = {
        "model": model,
        "tools": [
            {
                "type": "mcp",
                "server_label": "dadata",
                "server_url": DADATA_MCP_SERVER_URL,
                "headers": {"authorization": dadata_token},
                "require_approval": "never",
            }
        ],
        "input": (
            f"Получи данные о компании по ИНН или ОГРН: {query}. "
            "Нужны: полное название, ИНН, ОГРН, юридический адрес, "
            "контакты (email, телефон), статус. Верни только факты."
        ),
    }

    url = f"{openai_cfg['base_url']}/responses"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_cfg['api_key']}",
    }

    try:
        async with httpx.AsyncClient(
            timeout=90.0,
            proxy=settings.http_proxy_url,
        ) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 424:
            logger.warning(
                "Dadata MCP 424 Failed Dependency for %s: OpenAI не смог получить список инструментов "
                "с сервера Dadata (таймаут или недоступность с серверов OpenAI). Проверьте: 1) ключи Dadata, "
                "2) доступность https://mcp.dadata.ru/mcp (вызов GET /api/dadata-mcp/check). "
                "Обогащение по ИНН продолжается через REST API Dadata.",
                query,
            )
        else:
            logger.warning("Dadata MCP HTTP error for %s: %s %s", query, e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.warning("Dadata MCP request error for %s: %s", query, e)
        return None

    # Ответ Responses API: output — массив элементов; mcp_call содержит output от MCP
    output_items = data.get("output") or []
    for item in output_items:
        if item.get("type") == "mcp_call" and item.get("output") is not None:
            out = item["output"]
            if isinstance(out, str):
                try:
                    return json.loads(out)
                except json.JSONDecodeError:
                    return {"raw": out}
            if isinstance(out, dict):
                return out
            return {"raw": str(out)}

    # Если модель ответила текстом без вызова MCP
    output_text = data.get("output_text") or ""
    if output_text.strip():
        return {"raw": output_text.strip()}

    logger.info("Dadata MCP: no mcp_call in response for %s", query)
    return None


__all__ = ["enrich_company_with_mcp", "check_dadata_mcp_server"]
