"""Настройки поиска и лимитов Perplexity."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings

# Глобальных лимитов на поиск нет. 0 = все ключевые слова, большие значения = без ограничения числа источников/лидов.
DEFAULT_SETTINGS = {
    "perplexity_limit_sources": 100_000,
    "perplexity_limit_leads": 100_000,
    "perplexity_query_limit": 0,
}


def _settings_path() -> Path:
    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / "search_settings.json"


def get_search_settings() -> dict:
    path = _settings_path()
    if not path.exists():
        return DEFAULT_SETTINGS.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_SETTINGS.copy()
    merged = DEFAULT_SETTINGS.copy()
    merged.update({k: v for k, v in data.items() if v is not None})
    return merged


def update_search_settings(payload: dict) -> dict:
    current = get_search_settings()
    for key in DEFAULT_SETTINGS:
        if key not in payload:
            continue
        value = payload.get(key)
        if not isinstance(value, int):
            continue
        if key == "perplexity_query_limit":
            current[key] = max(0, min(100_000, value))
        else:
            current[key] = max(0, min(100_000, value))
    _settings_path().write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    return current
