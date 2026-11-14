"""Automation status and launch history.

Author: Maxi-online
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from app.core.config import get_settings


def _state_path() -> Path:
    """Get a path to the automation status file.

    :return: The way to JSON's status file.
    """

    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / "automation_state.json"


def _lock_path() -> Path:
    """Get a way to lockdown file.

    :return: Path to the lockdown file.
    """

    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / "automation.lock"


def _enrich_lock_path() -> Path:
    """Get a way to the refill lock file.

    :return: JSON's road to the refill lock file.
    """

    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / "automation_enrich.lock"


def get_state() -> dict:
    """Get the current status of automation.

    :return: Status dictionary.
    """

    path = _state_path()
    if not path.exists():
        return {"enabled": True, "last_run_at": None, "last_result": None}
    return json.loads(path.read_text(encoding="utf-8"))


def set_enabled(enabled: bool) -> dict:
    """Set up the automation flag.

    :param enabled: New flag of activation.
    :return: Updated state.
    """

    state = get_state()
    state["enabled"] = bool(enabled)
    _state_path().write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state


def update_last_run(result: dict) -> dict:
    """Update the latest launch information.

    :param results: Results of the last cycle.
    :return: Updated state.
    """

    state = get_state()
    state["last_run_at"] = datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None).isoformat()
    state["last_result"] = result
    _state_path().write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state


def is_enabled() -> bool:
    """Check if the automation is on.

    :return:True, if automation is on.
    """

    return bool(get_state().get("enabled", True))


def acquire_lock(ttl_seconds: int = 900) -> bool:
    """Grab the lock to start the cycle.

    :param ttl_seconds: Lifetime lock in seconds.
    :return:True if lock is received.
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
    """Unlock the cycle.

    :return: None.
    """

    path = _lock_path()
    if path.exists():
        path.unlink()


def acquire_enrich_lock(ttl_seconds: int = 300) -> bool:
    """Grab a block to refill the projects.

    :param ttl_seconds: Lifetime lock in seconds.
    :return:True if lock is received.
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
    """Unlock the refilling lock.

    :return: None.
    """

    path = _enrich_lock_path()
    if path.exists():
        path.unlink()
