"""Состояние автоматизации и история запусков.

Автор: Maxi-online
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from app.core.config import get_settings


def _state_path() -> Path:
    """Получить путь к файлу состояния автоматизации.

    :return: Путь к JSON файлу состояния.
    """

    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / "automation_state.json"


def _lock_path() -> Path:
    """Получить путь к файлу блокировки.

    :return: Путь к файлу блокировки.
    """

    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / "automation.lock"


def _enrich_lock_path() -> Path:
    """Получить путь к файлу блокировки дозаполнения.

    :return: Путь к JSON файлу блокировки дозаполнения.
    """

    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / "automation_enrich.lock"


def get_state() -> dict:
    """Получить текущее состояние автоматизации.

    :return: Словарь состояния.
    """

    path = _state_path()
    if not path.exists():
        return {"enabled": True, "last_run_at": None, "last_result": None}
    return json.loads(path.read_text(encoding="utf-8"))


def set_enabled(enabled: bool) -> dict:
    """Установить флаг автоматизации.

    :param enabled: Новый флаг включения.
    :return: Обновлённое состояние.
    """

    state = get_state()
    state["enabled"] = bool(enabled)
    _state_path().write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state


def update_last_run(result: dict) -> dict:
    """Обновить информацию о последнем запуске.

    :param result: Результат последнего цикла.
    :return: Обновлённое состояние.
    """

    state = get_state()
    state["last_run_at"] = datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None).isoformat()
    state["last_result"] = result
    _state_path().write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state


def is_enabled() -> bool:
    """Проверить, включена ли автоматизация.

    :return: True, если автоматизация включена.
    """

    return bool(get_state().get("enabled", True))


def acquire_lock(ttl_seconds: int = 900) -> bool:
    """Захватить блокировку для запуска цикла.

    :param ttl_seconds: Время жизни блокировки в секундах.
    :return: True если блокировка получена.
    """

    path = _lock_path()
    if path.exists():
        age_seconds = (
            datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
            - datetime.fromtimestamp(path.stat().st_mtime).replace(tzinfo=None)
        ).total_seconds()
        if age_seconds < ttl_seconds:
            return False
    path.write_text(
        datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None).isoformat(),
        encoding="utf-8",
    )
    return True


def release_lock() -> None:
    """Снять блокировку цикла.

    :return: None.
    """

    path = _lock_path()
    if path.exists():
        path.unlink()


def acquire_enrich_lock(ttl_seconds: int = 300) -> bool:
    """Захватить блокировку для дозаполнения проектов.

    :param ttl_seconds: Время жизни блокировки в секундах.
    :return: True если блокировка получена.
    """

    path = _enrich_lock_path()
    if path.exists():
        age_seconds = (
            datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
            - datetime.fromtimestamp(path.stat().st_mtime).replace(tzinfo=None)
        ).total_seconds()
        if age_seconds < ttl_seconds:
            return False
    path.write_text(
        datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None).isoformat(),
        encoding="utf-8",
    )
    return True


def release_enrich_lock() -> None:
    """Снять блокировку дозаполнения.

    :return: None.
    """

    path = _enrich_lock_path()
    if path.exists():
        path.unlink()
