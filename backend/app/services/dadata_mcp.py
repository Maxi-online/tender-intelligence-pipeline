"""Dadata via OpenAI Responses API + MCP (one configuration point: gpt-5-nano, Proxi)).

Documentation: https://dadata.ru/mcp/:
- server_url: https://mcp.dadata.ru/mcp
- Authorization: in headers, authoration: "Bearer ${API_KEY}: $ {SECRET_KEY}"
- OpenAI on call MCP transmits the current to the Dadata server; 424 = OpenAI failed to obtain
  server list (timeout, network or server response)).
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

# MCP Streamable HTTP: client sends JSON-RPC (initialize, then tools/list)).
# Dadata can support 2024-11-05 or 2025-03-26, with 400 samples.
MCP_PROTOCOL_VERSION = "2024-11-05"


def _parse_mcp_response(resp: httpx.Response) -> dict | None:
    'Select Response MCP: eitherapplication/json, eitherSSE (event/data: {...}).'
    text = resp.text or ""
    if not text.strip():
        return None
    # Attempted as JSON
    if resp.headers.get("content-type", "").startswith("application/json"):
        try:
            return resp.json()
        except json.JSONDecodeError:
            pass
    # SSE: rows "data: {...}" — We're gonna stick it all together data And we're freaking out
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
    'Dadata keys: first from settings.json (like OpenAI), then from env through get_settings().'
    settings = get_settings()
    try:
        cfg = _load_openai_settings(settings.openai_settings_path)
        api_key = cfg.get("dadata_api_key") or settings.dadata_api_key
        secret_key = cfg.get("dadata_secret_key") or settings.dadata_secret_key
        return (api_key or None, secret_key or None)
    except Exception:
        return (settings.dadata_api_key, settings.dadata_secret_key)


async def check_dadata_mcp_server() -> dict[str, Any]:
    """Check direct access to the MPData server (without OpenAI)).

    Sends initialise and tools/list on the MCP Streamable HTTP specification.
    Success: The server answers and returns the list of tools.
    Keys are taken from settings.json or env (as for enrich_company_with_mcp)).
    :return: {"ok": bool, "message": str, "tools_count": int | None, "error": str | None}
    """
    dadata_api_key, dadata_secret_key = _get_dadata_credentials()
    if not dadata_api_key or not dadata_secret_key:
        return {
            "ok": False,
            "message": 'Apply dadata_api_key and dadata_secret_key to config/settings.json or DADATA_API_KEY and DADATA_SECRET_KEY in env',
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
                    "message": 'MCP initialize: Could not debrief the answer',
                    "tools_count": None,
                    "error": (resp.text or "")[:500],
                }
            if "result" not in data and "error" in data:
                return {
                    "ok": False,
                    "message": 'MCP initialize: error from the server',
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
                    "message": 'MCP tools/list: Could not debrief the answer',
                    "tools_count": None,
                    "error": (resp2.text or "")[:500],
                }
            if "error" in data2:
                return {
                    "ok": False,
                    "message": 'MCP tools/list: server error',
                    "tools_count": None,
                    "error": str(data2.get("error")),
                }
            tools = data2.get("result", {}).get("tools") or []
            return {
                "ok": True,
                "message": 'MCP Datata server available, list of tools received',
                "tools_count": len(tools),
                "error": None,
            }
    except httpx.TimeoutException as e:
        return {
            "ok": False,
            "message": 'Timeout to MCP Datata',
            "tools_count": None,
            "error": str(e),
        }
    except Exception as e:
        return {
            "ok": False,
            "message": 'Error in verifying MCP Dadata',
            "tools_count": None,
            "error": str(e),
        }


async def enrich_company_with_mcp(query: str) -> dict[str, Any] | None:
    """Get INN/EDP company data through Datata MCP on documentation.

    OpenAI Responsions API with type=mcp (server_url Dadata)).
    The model itself calls MCP Datata; the result comes from output mcp_call.
    The dadata keys are taken from the same settings.json as OpenAI from fallback to env.
    """
    settings = get_settings()
    dadata_api_key, dadata_secret_key = _get_dadata_credentials()
    if not dadata_api_key or not dadata_secret_key:
        logger.warning(
            'Dadata MCP skipped: send dadata_api_key and dadata_secret_key to config/settings.json or DADATA_* to env'
        )
        return None
    if not settings.http_proxy_url:
        logger.warning('Dadata MCP skipped: HTTP_PROXY_URL mandatory for OpenAI')
        return None

    try:
        openai_cfg = _load_openai_settings(settings.openai_settings_path)
    except Exception as e:
        logger.warning("Dadata MCP skipped: could not load OpenAI settings: %s", e)
        return None

    model = settings.openai_model or openai_cfg.get("model") or "gpt-5-nano"
    # Dadata: "Bearer ${API_KEY}:${SECRET_KEY}" - see https://dadata.ru/mcp/
    dadata_token = f"Bearer {dadata_api_key}:{dadata_secret_key}"

    # DocumentationDadata https://dadata.ru/mcp/ Transmitted by"headers": {"authorization": "Bearer KEY:SECRET"}.
    # OpenAI transmits these headlines when called tools/list and tool calls on the MCP server.
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
            f"Get data on the OIN or OGN company: {query}. "
            'Needed: full name, INN, DEA, legal address, '
            'Contacts (email, telephone), status. Give me back the facts.'
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
                'Dadata MCP 424 Failed Dependency for %s: OpenAI failed to obtain a list of tools '
                "Dadata server (timeout or non-access from OpenAI servers)). Check: 1) Dadata's Keys, "
                '(2) Availability of https://mcp.dadata.ru/mcp (GET call /api/dadata-mcp/check)). '
                'Enrichment by INN continues through REST API Dadata.',
                query,
            )
        else:
            logger.warning("Dadata MCP HTTP error for %s: %s %s", query, e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.warning("Dadata MCP request error for %s: %s", query, e)
        return None

    # Responsions API response: output is an array of elements; mcp_call contains an output from MCP
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

    # If the model responded by text without calling MCP
    output_text = data.get("output_text") or ""
    if output_text.strip():
        return {"raw": output_text.strip()}

    logger.info("Dadata MCP: no mcp_call in response for %s", query)
    return None


__all__ = ["enrich_company_with_mcp", "check_dadata_mcp_server"]
