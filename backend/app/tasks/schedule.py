"""Расписание задач Celery Beat.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import timedelta

from app.core.config import get_settings
from app.tasks.celery_app import celery_app

settings = get_settings()
interval_seconds = int(24 * 60 * 60 / max(settings.update_cycles_per_day, 1))

celery_app.conf.beat_schedule = {
    "update-cycle": {
        "task": "tpis.update_cycle",
        "schedule": timedelta(seconds=interval_seconds),
    },
    "discover-sources": {
        "task": "tpis.discover_sources_cycle",
        "schedule": timedelta(seconds=interval_seconds),
    },
}
