"""Analysis jobs: long computations run in the background, followed live from the dashboard.

| Kind | What it does |
| --- | --- |
| ``commune`` | full preparation of a commune: built-up fusion 1985 → today (WSF, Sentinel-2, footprints), roads, protected areas, watch alerts |
| ``sync`` | open-data synchronisation (statistics, schools, facilities) |

Inline mode runs a job in a thread of the API process; workers mode sends it to the
``analysis`` Celery queue. One job per commune at a time (shared lock).
"""

from __future__ import annotations

import datetime
import json
import logging
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from app.config import Settings, get_settings
from app.core import audit, shared
from app.db import db, lock, read_db, row, rows

logger = logging.getLogger(__name__)

KINDS = {"commune": "Préparation de la commune (satellite, bâti, routes, contraintes)",
         "sync": "Synchronisation des données ouvertes"}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _job(r: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if r is None:
        return None
    r = dict(r)
    for key in ("params", "steps", "summary"):
        r[key] = json.loads(r.get(key) or ("[]" if key == "steps" else "{}"))
    r["kind_label"] = KINDS.get(r["kind"], r["kind"])
    return r


def get(job_id: int, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    with read_db(settings) as conn:
        return _job(row(conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()))


def recent(commune: Optional[str] = None, limit: int = 30, settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM analysis_jobs"
    params: List[Any] = []
    if commune:
        query += " WHERE commune_code = ?"
        params.append(commune)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with read_db(settings) as conn:
        return [_job(r) for r in rows(conn.execute(query, params).fetchall())]  # type: ignore[misc]


# Longest a job may run (Celery hard limit) / wait in the queue before it is considered lost.
RUN_TIMEOUT = datetime.timedelta(hours=4, minutes=15)
QUEUE_TIMEOUT = datetime.timedelta(hours=12)


def expire_stale(settings: Optional[Settings] = None, interrupted: bool = False) -> int:
    """Mark lost jobs as failed so that their commune can be analysed again; returns how many.

    ``interrupted=True`` (start of an inline-mode process): every queued / running job belonged to
    the previous process and died with it. Otherwise only jobs past their time limit are expired.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    expired = 0
    with db(settings) as conn:
        for r in conn.execute("SELECT id, status, created_at, started_at FROM analysis_jobs WHERE status IN ('queued','running')").fetchall():
            reference = r["started_at"] if r["status"] == "running" and r["started_at"] else r["created_at"]
            age = now - datetime.datetime.fromisoformat(reference)
            limit = RUN_TIMEOUT if r["status"] == "running" else QUEUE_TIMEOUT
            if interrupted or age > limit:
                reason = "interrompue par un redémarrage de la plateforme" if interrupted else "délai maximal dépassé (processus perdu)"
                conn.execute("UPDATE analysis_jobs SET status = 'failed', finished_at = ?, message = ? WHERE id = ?",
                             (now.isoformat(), f"Échec : analyse {reason} — relancez-la", r["id"]))
                expired += 1
    if expired:
        logger.warning("%s analysis job(s) marked as failed (%s)", expired, "restart" if interrupted else "timeout")
    return expired


def active(commune: str, kind: str, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    expire_stale(settings)
    with read_db(settings) as conn:
        r = conn.execute("SELECT * FROM analysis_jobs WHERE commune_code = ? AND kind = ? AND status IN ('queued','running') "
                         "ORDER BY id DESC LIMIT 1", (commune, kind)).fetchone()
    return _job(row(r))


def create(kind: str, commune: str, params: Dict[str, Any], actor: str, settings: Optional[Settings] = None) -> Dict[str, Any]:
    if kind not in KINDS:
        raise ValueError("Type d'analyse inconnu")
    expire_stale(settings)
    with db(settings) as conn:
        # Check and insert in the same write transaction (serialised across processes): two clicks,
        # or the scheduler and an analyst at once, never queue the same work twice.
        lock(conn, f"job:{kind}:{commune}")
        pending = conn.execute("SELECT id FROM analysis_jobs WHERE commune_code = ? AND kind = ? AND status IN ('queued','running') "
                               "ORDER BY id DESC LIMIT 1", (commune, kind)).fetchone()
        if pending is None:
            cur = conn.execute(
                "INSERT INTO analysis_jobs (kind, commune_code, params, status, created_at, created_by) VALUES (?, ?, ?, 'queued', ?, ?) RETURNING id",
                (kind, commune, json.dumps(params), _now(), actor),
            )
            job_id = int(cur.fetchone()[0])
    if pending is not None:
        running = get(int(pending["id"]), settings)
        assert running is not None
        return {**running, "created": False}  # same work already pending: never queued twice
    audit.record("analysis.start", actor=actor, target=f"job:{job_id}", details={"kind": kind, "commune": commune, **params},
                 settings=settings)
    job = get(job_id, settings)
    assert job is not None
    return {**job, "created": True}


def _update(job_id: int, settings: Optional[Settings], **fields: Any) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)
    values = [json.dumps(v) if k in ("steps", "summary", "params") else v for k, v in fields.items()]
    with db(settings) as conn:
        conn.execute(f"UPDATE analysis_jobs SET {sets} WHERE id = ?", (*values, job_id))


class Progress:
    """Records steps and progress of a job (throttled database writes)."""

    MIN_INTERVAL_S = 1.0

    def __init__(self, job_id: int, settings: Optional[Settings]) -> None:
        self.job_id, self.settings = job_id, settings
        self.steps: List[Dict[str, Any]] = []
        self._written_at = 0.0

    def __call__(self, message: str, pct: int) -> None:
        new_step = not self.steps or self.steps[-1]["message"] != message
        if new_step:
            self.steps.append({"at": _now(), "message": message})
        pct = max(0, min(100, int(pct)))
        now = time.monotonic()
        # A new step or the end is always written; plain percentage ticks at most once a second
        # (a satellite series reports progress per block: each write takes the database write lock).
        if new_step or pct >= 100 or now - self._written_at >= self.MIN_INTERVAL_S:
            self._written_at = now
            _update(self.job_id, self.settings, progress=pct, message=message, steps=self.steps[-40:])


def run(job_id: int, settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Execute a job synchronously (called by the worker or the inline thread)."""
    cfg = settings or get_settings()
    job = get(job_id, cfg)
    if job is None:
        raise LookupError("Analyse introuvable")
    lock = f"job:{job['kind']}:{job['commune_code']}"
    if not shared.acquire(lock, 4 * 3600):
        _update(job_id, cfg, status="failed", message="Une autre analyse de cette commune est en cours", finished_at=_now())
        return {}
    progress = Progress(job_id, cfg)
    _update(job_id, cfg, status="running", started_at=_now(), progress=0)
    try:
        if job["kind"] == "commune":
            summary = prepare_commune(job["commune_code"], job["params"], cfg, progress)
        else:
            from app.territoire import sync

            summary = sync.run(job["created_by"], cfg, progress=progress)
        _update(job_id, cfg, status="done", progress=100, finished_at=_now(), summary=summary, message="Terminé")
        audit.record("analysis.done", actor=job["created_by"], target=f"job:{job_id}", details={"kind": job["kind"]}, settings=cfg)
        return summary
    except Exception as exc:
        logger.exception("Analysis job %s failed", job_id)
        _update(job_id, cfg, status="failed", finished_at=_now(), message=f"Échec : {str(exc)[:300]}")
        audit.record("analysis.done", actor=job["created_by"], target=f"job:{job_id}", outcome="failure",
                     details={"error": str(exc)[:200]}, settings=cfg)
        from app.services import notify

        notify.notify_event("analyses", f"Analyse en échec — {job['kind_label']} ({job['commune_code']})", level="danger",
                            details={"Erreur": str(exc)[:300]}, view="analyses", label="Analyses", settings=cfg)
        return {"error": str(exc)}
    finally:
        shared.release(lock)


def dispatch(job: Dict[str, Any], settings: Optional[Settings] = None) -> None:
    """Start a job in the background (Celery queue in workers mode, thread otherwise)."""
    cfg = settings or get_settings()
    if cfg.background_mode == "workers":
        try:
            from app.tasks import analysis

            analysis.apply_async(args=[job["id"]], queue="analysis")
            return
        except Exception as exc:  # broker down: run here rather than lose the request
            logger.warning("Analysis queue unavailable (%s): running inline", type(exc).__name__)
    threading.Thread(target=run, args=(job["id"], cfg), daemon=True).start()


# --------------------------------------------------------------------------- commune preparation


def _road_cells(bbox: Any, cfg: Settings) -> List[str]:
    """Cells crossed by an OSM road (points every ~50 m along each segment)."""
    from app.analyse.grid import cell_id, cell_of
    from app.sources import osm

    cells = set()
    for line in osm.roads(bbox, cfg):
        for (x1, y1), (x2, y2) in zip(line, line[1:]):
            length = math.hypot((x2 - x1) * 111_000, (y2 - y1) * 111_000)
            steps = max(1, int(length / 50))
            for s in range(steps + 1):
                t = s / steps
                cells.add(cell_id(*cell_of(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)))
    return sorted(cells)


def prepare_commune(commune_code: str, params: Dict[str, Any], cfg: Settings, progress: Callable[[str, int], None]) -> Dict[str, Any]:
    from app.analyse import builtup, layers as layer_store, watch
    from app.core.geo import simplify_geometry
    from app.services import notify
    from app.sources import osm, protected
    from app.territoire import store

    commune = store.commune(commune_code, cfg)
    if commune is None:
        raise LookupError("Commune inconnue")

    def scaled(lo: int, hi: int) -> Callable[[str, int], None]:
        return lambda message, pct: progress(message, lo + int((hi - lo) * pct / 100))

    meta = builtup.fuse(commune_code, commune["contour"], cfg, progress=scaled(0, 80),
                        with_sentinel2=bool(params.get("sentinel2", True)))
    progress("Réseau routier (OpenStreetMap)", 82)
    road_info: Dict[str, Any] = {}
    try:
        windows = meta["windows"]["windows"] or [commune["bbox"]]
        bbox = (min(w[0] for w in windows), min(w[1] for w in windows), max(w[2] for w in windows), max(w[3] for w in windows))
        road_cells = _road_cells(bbox, cfg)
        layer_store.save(commune_code, "roads", road_cells, {"source": "OpenStreetMap", "cells": len(road_cells)}, cfg)
        road_info = {"cells": len(road_cells)}
    except osm.OverpassError as exc:
        road_info = {"error": str(exc)}
    progress("Aires protégées (WDPA)", 88)
    try:
        areas = protected.areas(commune["bbox"], cfg)
        simplified = [{**a, "geometry": simplify_geometry(a["geometry"], 0.002)} for a in areas]
        layer_store.save(commune_code, "protected", simplified, {"source": "WDPA (UNEP-WCMC/UICN)", "areas": len(areas)}, cfg)
    except Exception as exc:
        areas = []
        logger.warning("WDPA unavailable for %s: %s", commune_code, exc)
    progress("Quartiers INSEE (IRIS) : population et âges par quartier", 92)
    iris_info: Dict[str, Any] = {}
    try:
        from app.sources import iris

        layer = iris.commune_layer(commune_code, cfg)
        if layer:
            layer_store.save(commune_code, "iris", layer, {"source": layer["source"], "zones": len(layer["zones"])}, cfg)
            iris_info = {"zones": len(layer["zones"]), "unmatched": len(layer["unmatched"]), "year": layer["year"]}
    except Exception as exc:  # optional refinement: the commune-level calibration remains
        iris_info = {"error": str(exc)[:200]}
        logger.warning("IRIS unavailable for %s: %s", commune_code, exc)
    progress("Veille : croissance loin des équipements", 94)
    alerts = watch.hotspots(commune_code, cfg)
    from app.analyse import satellite

    summary = {
        "built_ha": meta["totals_ha"], "calibration": meta.get("calibration"), "observed_years": meta.get("observed_years"),
        "quality": satellite.grade(meta.get("calibration")),
        "errors": meta.get("errors"), "windows": meta.get("windows"), "buildings_total": meta.get("buildings_total"),
        "roads": road_info, "protected_areas": len(areas), "alerts": alerts.get("summary"), "iris": iris_info,
    }
    calib = meta.get("calibration") or {}
    totals = meta.get("totals_ha") or {}
    years = sorted(int(y) for y in totals)
    last_year = years[-1] if years else None
    notify.notify_event(
        "analyses", f"Analyse satellitaire terminée — {commune['nom']}", level="success",
        details={"Surface bâtie 2019 (ha)": totals.get("2019"),
                 f"Surface bâtie {last_year or '—'} (ha)": totals.get(str(last_year)) if last_year else None,
                 "Concordance avec WSF 2019": f"{calib['concordance']:.0%}" if calib.get("concordance") is not None else "—",
                 "Années observées": ", ".join(str(y) for y in meta.get("observed_years") or []) or "aucune"},
        view=f"atlas/{commune_code}", label="Ouvrir l'atlas", settings=cfg,
    )
    progress("Terminé", 100)
    return summary
