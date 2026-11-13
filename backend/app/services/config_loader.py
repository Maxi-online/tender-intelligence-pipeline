"""Загрузка конфигурационных файлов YAML.

Автор: Maxi-online
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.core.config import get_settings


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




def _resolve_config_path(path: str) -> Path:
    """Найти конфиг: сначала относительно cwd, затем /app (Docker)."""
    p = Path(path)
    if p.is_absolute() and p.is_file():
        return p
    if p.is_file():
        return p
    docker_path = Path("/app") / path
    if docker_path.is_file():
        return docker_path
    raise FileNotFoundError(f"Файл не найден: {path} (проверены cwd и /app)")


def load_yaml(path: str) -> dict[str, Any]:
    """Загрузить YAML файл и вернуть словарь.

    :param path: Путь к YAML файлу.
    :return: Содержимое YAML в виде словаря.
    """

    resolved = _resolve_config_path(path)
    with resolved.open("r", encoding="utf-8") as file:
        return _resolve_settings_env(yaml.safe_load(file)) or {}


def load_sources_config() -> list[dict[str, Any]]:
    """Загрузить список источников из конфигурации.

    :return: Список источников.
    """

    settings = get_settings()
    data = load_yaml(settings.sources_config_path)
    return data.get("sources", [])


def load_keywords_config() -> dict[str, list[str]]:
    """Загрузить словари ключевых слов.

    :return: Словарь ключевых слов.
    """

    settings = get_settings()
    data = load_yaml(settings.keywords_config_path)
    return {
        "construction_keywords": data.get("construction_keywords", []),
        "regions": data.get("regions", []),
    }
