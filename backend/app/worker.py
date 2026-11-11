"""Celery application: background work outside the API process (scalable deployment).

Queues
------
``analysis``  commune preparation (satellite series) and open-data syncs — heavy, one at a time
``default``   source health watch, hourly audit check, scheduled data refresh
``notify``    webhook deliveries, retried with exponential backoff

Broker: ``CELERY_BROKER_URL`` if set (e.g. ``amqp://`` for RabbitMQ), otherwise Redis
(``REDIS_URL``). No result backend: jobs report through the database (analysis_jobs),
the shared state and the audit trail.

Start::

    celery -A app.worker worker -Q default,notify     # general worker
    celery -A app.worker worker -Q analysis -c 1       # analysis worker
    celery -A app.worker beat                          # scheduler
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings
from app.core.shared import redis_url


def broker_url() -> str:
    cfg = get_settings()
    return cfg.celery_broker_url or redis_url(cfg) or "memory://"


celery_app = Celery("kap", broker=broker_url(), include=["app.tasks"])
celery_app.conf.update(
    task_default_queue="default",
    task_routes={"kap.analysis": {"queue": "analysis"}, "kap.notify": {"queue": "notify"}},
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 5 * 3600},  # > longest analysis
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "sources": {"task": "kap.sources", "schedule": 60.0, "options": {"expires": 55}},
        "hourly": {"task": "kap.hourly", "schedule": 3600.0, "options": {"expires": 3000}},
    },
    beat_schedule_filename="/tmp/celerybeat-schedule",
    worker_hijack_root_logger=False,
)
