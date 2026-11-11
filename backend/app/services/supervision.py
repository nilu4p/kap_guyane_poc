"""Technical supervision board: is the platform itself healthy, fast and up to date?

External sources (last success / failure, consecutive errors), freshness of the open
data, analysis jobs (duration, failures), API response times per area, database and
disk usage. Everything is read locally — no external call — so the board stays
available when the sources are not.
"""

from __future__ import annotations

import datetime
import os
import shutil
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from app.config import Settings, get_settings
from app.db import is_postgres, read_db

_lock = threading.Lock()
_timings: Dict[str, Deque[Tuple[float, int]]] = defaultdict(lambda: deque(maxlen=500))
STARTED_AT = datetime.datetime.now(datetime.timezone.utc)


def area_of(path: str, prefix: str) -> Optional[str]:
    """``/api/v1/grille/97311/layers`` → ``grille``."""
    if not path.startswith(prefix + "/"):
        return None
    head = path[len(prefix) + 1:].split("/", 1)[0]
    return head or None


def record_timing(area: str, seconds: float, status: int) -> None:
    with _lock:
        _timings[area].append((seconds, status))


def api_timings() -> List[Dict[str, Any]]:
    with _lock:
        snapshot_ = {area: list(values) for area, values in _timings.items()}
    result = []
    for area, values in snapshot_.items():
        durations = sorted(v[0] for v in values)
        if not durations:
            continue
        pick = lambda q: durations[min(len(durations) - 1, int(q * len(durations)))]  # noqa: E731
        result.append({
            "area": area, "requests": len(values), "p50_ms": round(pick(0.5) * 1000), "p95_ms": round(pick(0.95) * 1000),
            "max_ms": round(durations[-1] * 1000), "errors": sum(1 for v in values if v[1] >= 500),
        })
    return sorted(result, key=lambda r: r["p95_ms"], reverse=True)


def _dir_size(path: Path, limit_files: int = 200_000) -> Optional[int]:
    total, count = 0, 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                count += 1
                if count > limit_files:
                    return None
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        return None
    return total


def _database(cfg: Settings) -> Dict[str, Any]:
    from app.db import TABLES

    info: Dict[str, Any] = {"engine": "postgresql" if is_postgres(cfg) else "sqlite"}
    with read_db(cfg) as conn:
        counts = {}
        for table in TABLES:
            try:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except Exception:
                counts[table] = None
        info["rows"] = counts
        if info["engine"] == "postgresql":
            try:
                info["size_bytes"] = conn.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            except Exception:
                info["size_bytes"] = None
    if info["engine"] == "sqlite":
        info["size_bytes"] = sum(p.stat().st_size for p in Path(cfg.data_dir).glob("kap.db*")) or None
    return info


# Folder sizes walk up to 200 000 files (the tile cache): measured at most every 5 minutes,
# not on every refresh of the board (every 15 s per open screen).
DISK_SIZES_TTL_S = 300.0
_sizes_cache: Dict[Tuple[str, ...], Tuple[float, Dict[str, Optional[int]]]] = {}


def _folder_sizes(folders: Dict[str, Path]) -> Dict[str, Optional[int]]:
    key = tuple(f"{name}={path}" for name, path in sorted(folders.items()))
    now = time.monotonic()
    with _lock:
        cached = _sizes_cache.get(key)
    if cached and now - cached[0] < DISK_SIZES_TTL_S:
        return dict(cached[1])
    sizes = {name: _dir_size(Path(path)) for name, path in folders.items()}
    with _lock:
        _sizes_cache[key] = (now, sizes)
    return dict(sizes)


def _disk(cfg: Settings) -> Dict[str, Any]:
    folders = {"cache": cfg.cache_dir, "backups": cfg.backup_dir, "data": cfg.data_dir}
    result: Dict[str, Any] = _folder_sizes(folders)
    try:
        usage = shutil.disk_usage(cfg.data_dir)
        result["free_bytes"], result["total_bytes"] = usage.free, usage.total
    except OSError:
        result["free_bytes"] = result["total_bytes"] = None
    return result


def _age_s(stamp: Optional[str], now: datetime.datetime) -> Optional[float]:
    if not stamp:
        return None
    try:
        return round((now - datetime.datetime.fromisoformat(stamp)).total_seconds())
    except ValueError:
        return None


def snapshot(settings: Optional[Settings] = None) -> Dict[str, Any]:
    from app.analyse import jobs
    from app.sources import health
    from app.territoire import store

    cfg = settings or get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    t0 = time.monotonic()
    sources = []
    for name, entry in sorted(health.snapshot().items()):
        sources.append({"source": name, **entry, "success_age_s": _age_s(entry.get("last_success"), now),
                        "failure_age_s": _age_s(entry.get("last_failure"), now)})
    recent = jobs.recent(limit=30, settings=cfg)
    durations = []
    for j in recent:
        if j["status"] == "done" and j.get("started_at") and j.get("finished_at"):
            durations.append((datetime.datetime.fromisoformat(j["finished_at"]) - datetime.datetime.fromisoformat(j["started_at"])).total_seconds())
    return {
        "generated_at": now.isoformat(),
        "process_started_at": STARTED_AT.isoformat(),
        "background_mode": cfg.background_mode,
        "environment": cfg.environment,
        "sources": sources,
        "data": store.data_freshness(cfg),
        "jobs": {"recent": [{k: j[k] for k in ("id", "kind", "commune_code", "status", "created_at", "finished_at", "message")}
                            for j in recent[:10]],
                 "average_duration_s": round(sum(durations) / len(durations)) if durations else None,
                 "failed_recent": sum(1 for j in recent[:10] if j["status"] == "failed"),
                 "running": sum(1 for j in recent if j["status"] in ("queued", "running"))},
        "api": api_timings(),
        "database": _database(cfg),
        "disk": _disk(cfg),
        "built_in_ms": round((time.monotonic() - t0) * 1000),
    }
