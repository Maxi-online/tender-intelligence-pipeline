"""Клиент OpenAI (fallback) через AsyncOpenAI."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.core.config import get_settings

import logging


def _resolve_settings_env(value):
    """Resolve required environment references in already parsed configuration."""
    import os
    import re
    if isinstance(value, dict):
        return {key: _resolve_settings_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_settings_env(item) for item in value]
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"\$\{([A-Z_][A-Z0-9_]*)(?::(int|float|bool))?\}", value)
    if match is None:
        return value
    name, kind = match.groups()
    content = os.environ.get(name)
    if content is None or not content.strip():
        raise RuntimeError(f"Required configuration variable is missing: {name}")
    if kind == "int":
        return int(content)
    if kind == "float":
        return float(content)
    if kind == "bool":
        if content.lower() not in {"true", "false", "1", "0"}:
            raise ValueError(f"Expected a boolean configuration variable: {name}")
        return content.lower() in {"true", "1"}
    return content



logger = logging.getLogger(__name__)


@lru_cache
def _load_openai_settings(path: str) -> dict[str, str]:
    settings_path = Path(path)
    if not settings_path.is_absolute():
        candidates = [
            settings_path,
            Path("/app") / settings_path,
            Path("/app/config/settings.json"),
        ]
    else:
        candidates = [settings_path]
    for candidate in candidates:
        if candidate.exists():
            settings_path = candidate
            break
    else:
        raise RuntimeError(
            f"OpenAI settings file not found. Tried: {', '.join(str(p) for p in candidates)}"
        )
    data = _resolve_settings_env(json.loads(settings_path.read_text(encoding="utf-8")))
    api_key = data.get("openai_api_key") or data.get("api_key")
    if not api_key:
        raise RuntimeError("OpenAI API key not found in settings.json")
    model = data.get("openai_model") or "gpt-5-nano"
    base_url = data.get("openai_base_url") or "https://api.openai.com/v1"
    # Ключи Dadata из того же файла (опционально), чтобы не зависеть от env в контексте, где он недоступен
    dadata_api_key = data.get("dadata_api_key") or ""
    dadata_secret_key = data.get("dadata_secret_key") or ""
    return {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "dadata_api_key": dadata_api_key.strip() or None,
        "dadata_secret_key": dadata_secret_key.strip() or None,
    }


class OpenAIClient:
    """Клиент OpenAI: все запросы отправляются только через прокси (HTTP_PROXY_URL)."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.http_proxy_url:
            raise RuntimeError("HTTP_PROXY_URL обязателен: запросы к OpenAI идут только через прокси.")
        cfg = _load_openai_settings(settings.openai_settings_path)
        self._model = cfg["model"]
        self._client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            http_client=httpx.AsyncClient(
                timeout=120.0,
                proxy=settings.http_proxy_url,
            ),
        )

    async def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        reasoning_effort: str | None = None,
        **extra_create_kwargs: Any,
    ) -> dict[str, Any]:
        """Запрос к OpenAI (всегда через прокси). reasoning_effort: low | medium | high | xhigh (макс. качество рассуждений)."""
        logger.info(
            "OpenAI call: model=%s system_len=%s messages=%s reasoning_effort=%s",
            self._model,
            len(system),
            len(messages),
            reasoning_effort,
        )
        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        if reasoning_effort is not None:
            create_kwargs["reasoning_effort"] = reasoning_effort
        create_kwargs.update(extra_create_kwargs)
        response = await self._client.chat.completions.create(**create_kwargs)
        content = response.choices[0].message.content or ""
        logger.info("OpenAI response length: %s", len(str(content)))
        return {"content": [{"type": "text", "text": str(content)}]}
