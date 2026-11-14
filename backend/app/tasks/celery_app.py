"""Initialization of Celery Applications.

Author: Maxi-online
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tpis",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Moscow",
    enable_utc=False,
)

# Recording of tasks and schedules.
from app.tasks import jobs as _jobs  # noqa: F401
from app.tasks import schedule as _schedule  # noqa: F401
