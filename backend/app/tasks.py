"""Celery tasks: thin wrappers around the same functions the inline mode runs.

Every task first reloads the keys and operational settings saved from the dashboard
(another process may have changed them), then does its job.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import get_settings
from app.core import shared
from app.worker import celery_app

logger = logging.getLogger(__name__)


def refresh_settings() -> Any:
    from app.core.credentials import apply_stored_credentials
    from app.services import runtime

    cfg = get_settings()
    apply_stored_credentials(cfg)
    runtime.apply_stored(cfg)
    return cfg


def _exclusive(name: str, ttl: float, job: Any) -> Any:
    if not shared.acquire(f"tick:{name}", ttl):
        logger.info("Tick %s still running elsewhere: skipped", name)
        return None
    try:
        return job()
    finally:
        shared.release(f"tick:{name}")


@celery_app.task(name="kap.analysis", acks_late=True, time_limit=4 * 3600, soft_time_limit=4 * 3600 - 300)
def analysis(job_id: int) -> Any:
    from app.analyse import jobs

    return jobs.run(job_id, refresh_settings())


@celery_app.task(name="kap.sources")
def sources_tick() -> Any:
    from app.services.scheduler import watch_sources

    return _exclusive("sources", 300, lambda: watch_sources(refresh_settings()))


@celery_app.task(name="kap.hourly", time_limit=2 * 3600)
def hourly() -> None:
    from app.services.scheduler import check_audit_chain, refresh_data_if_due

    cfg = refresh_settings()
    check_audit_chain(cfg)
    _exclusive("data_refresh", 2 * 3600, lambda: refresh_data_if_due(cfg))


@celery_app.task(name="kap.notify", bind=True, max_retries=6, acks_late=True)
def notify(self: Any, url: str, payload: Dict[str, Any]) -> bool:
    """Webhook delivery; retried 30 s, 1, 2, 4, 8, 16 min before giving up."""
    from app.services.notify import _post

    if _post(url, payload, get_settings()):
        return True
    raise self.retry(countdown=min(30 * 2 ** self.request.retries, 960))
