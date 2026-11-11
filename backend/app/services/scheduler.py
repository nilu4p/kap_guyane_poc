"""Periodic duties: open-data refresh, source health watch, audit-chain integrity.

In inline mode :func:`background_loop` runs them inside the API process; in workers
mode Celery beat triggers the same functions (``app.tasks``).
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Dict, Optional

from app.config import Settings, get_settings
from app.core import shared

logger = logging.getLogger(__name__)


def watch_sources(settings: Optional[Settings] = None) -> int:
    """Notify once when a source goes down (3 consecutive failures) or comes back; returns notifications sent."""
    from app.services import notify
    from app.sources import health

    cfg = settings or get_settings()
    sent = 0
    for name, entry in health.snapshot().items():
        status = entry["status"]
        previous = shared.hget_json("health_notified", name)
        if status == "down" and previous != "down":
            notify.notify_source_health(name, "down", entry.get("last_error", ""), cfg)
            shared.hset_json("health_notified", name, "down")
            sent += 1
        elif status == "ok" and previous == "down":
            notify.notify_source_health(name, "ok", settings=cfg)
            shared.hset_json("health_notified", name, "ok")
            sent += 1
    return sent


def check_audit_chain(settings: Optional[Settings] = None) -> bool:
    from app.core import audit
    from app.services import notify

    cfg = settings or get_settings()
    result = audit.verify_chain(cfg)
    if not result.get("valid"):
        notify.notify_event("securite", "🔐 Journal d'audit ALTÉRÉ — chaîne de hachage rompue", level="danger",
                            details={"Première entrée invalide": result.get("broken_at")}, view="audit", label="Journal d'audit",
                            key="audit:broken", cooldown=24 * 3600, settings=cfg)
    return bool(result.get("valid"))


def refresh_data_if_due(settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    """Open-data synchronisation when the last one is older than ``data_refresh_days``."""
    from app.analyse import jobs

    cfg = settings or get_settings()
    if cfg.data_refresh_days <= 0:
        return None
    last = next((j for j in jobs.recent(cfg.department_code, 10, cfg) if j["kind"] == "sync" and j["status"] == "done"), None)
    if last:
        finished = datetime.datetime.fromisoformat(last["finished_at"])
        if datetime.datetime.now(datetime.timezone.utc) - finished < datetime.timedelta(days=cfg.data_refresh_days):
            return None
    if not shared.first_in("auto_sync", 3600):
        return None
    job = jobs.create("sync", cfg.department_code, {"auto": True}, "system", cfg)
    if job["created"]:
        jobs.run(job["id"], cfg)
    return job


async def background_loop(settings: Optional[Settings] = None) -> None:
    """Inline mode: source watch every minute, audit check hourly, data refresh when due."""
    cfg = settings or get_settings()
    minute = 0
    while True:
        try:
            await asyncio.to_thread(watch_sources, cfg)
            if minute % 60 == 0:
                await asyncio.to_thread(check_audit_chain, cfg)
                await asyncio.to_thread(refresh_data_if_due, cfg)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Background duty failed")
        minute += 1
        await asyncio.sleep(60)
