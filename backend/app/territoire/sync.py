"""Synchronisation of the open data: communes, statistics, schools, everyday facilities.

Run by an analyst from the dashboard, by the scheduler every ``data_refresh_days``,
or by ``make sync``. Each source is independent: a source down leaves its previous
values in place and the report says so.

**Offline snapshot** — ``reference/snapshot_973.json.gz`` holds a copy of the
statistics and facilities taken from the same sources (date and origin inside). A
brand new instance loads it at first start so it can be demonstrated without any
network (salon, field visit); the first live synchronisation replaces it.
"""

from __future__ import annotations

import datetime
import gzip
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.config import Settings, get_settings
from app.territoire import indicators, store

logger = logging.getLogger(__name__)

SNAPSHOT = Path(__file__).resolve().parents[1] / "reference" / "snapshot_973.json.gz"


def digest_path(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")
SCHOOL_CATEGORY = {"Ecole": "ecole", "Collège": "college", "Lycée": "lycee"}


def _locator(settings: Settings) -> Callable[[float, float], Optional[str]]:
    """Point → commune code (prepared commune polygons)."""
    import shapely
    from shapely.geometry import shape

    polys = []
    for c in store.communes(settings, with_contour=True):
        geom = shape(c["contour"])
        shapely.prepare(geom)
        polys.append((c["code"], geom))

    def locate(lon: float, lat: float) -> Optional[str]:
        for code, geom in polys:
            if shapely.contains_xy(geom, lon, lat):
                return code
        return None

    return locate


def school_equipments(settings: Settings, live: bool = True) -> List[Dict[str, Any]]:
    from app.sources import education

    schools = education.schools(settings, live=live)
    try:
        latest = education.latest_by_school(education.enrolments(settings, live=live))
    except education.EducationError:
        latest = {}
    out = []
    for s in schools:
        category = SCHOOL_CATEGORY.get(s["type"])
        if not category:
            continue  # EREA, information centres… not a neighbourhood school
        enrol = latest.get(s["uai"] or "")
        subtype = "maternelle" if s["maternelle"] and not s["elementaire"] else (
            "elementaire" if s["elementaire"] and not s["maternelle"] else ("primaire" if category == "ecole" else category))
        attributes = {"uai": s["uai"], "public": s["public"], "nature": s["nature"],
                      "education_prioritaire": s["education_prioritaire"], "precision": s["precision"]}
        if enrol:
            attributes.update({"rentree": enrol["year"], "eleves": enrol["eleves"], "classes": enrol["classes"],
                               "historique_eleves": {str(k): v for k, v in enrol["history"].items()}})
        out.append({
            "uid": f"uai:{s['uai']}", "category": category, "subtype": subtype, "name": s["name"],
            "commune": s["commune"], "lat": s["lat"], "lon": s["lon"],
            "capacity": float(enrol["eleves"]) if enrol else None, "capacity_unit": "élèves inscrits" if enrol else "",
            "attributes": attributes,
        })
    return out


def finess_equipments(settings: Settings, live: bool = True) -> List[Dict[str, Any]]:
    from app.sources import finess

    locate = _locator(settings)
    out = []
    for f in finess.establishments(settings, live=live):
        f["commune"] = locate(f["lon"], f["lat"])
        if f["commune"]:
            out.append(f)
    return out


def osm_equipments(settings: Settings, live: bool = True, official_health: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """OSM facilities; health places within 60 m of an official FINESS establishment are dropped (same place twice)."""
    import numpy as np

    from app.analyse.grid import haversine_m
    from app.sources import osm

    locate = _locator(settings)
    official = official_health or []
    lons = np.array([f["lon"] for f in official])
    lats = np.array([f["lat"] for f in official])
    out = []
    for f in osm.facilities(settings, live=live):
        if f["category"] == "sante" and official and float(haversine_m(f["lon"], f["lat"], lons, lats).min()) < 60:
            continue
        f["commune"] = locate(f["lon"], f["lat"])
        if f["commune"]:
            out.append(f)
    return out


def run(actor: str = "system", settings: Optional[Settings] = None, live: bool = True,
        progress: Optional[Callable[[str, int], None]] = None) -> Dict[str, Any]:
    """Full synchronisation; returns a per-source report (also audited and notified)."""
    from app.core import audit
    from app.services import notify
    from app.sources import geoapi

    cfg = settings or get_settings()
    step = progress or (lambda _m, _p: None)
    report: List[Dict[str, Any]] = []
    started = datetime.datetime.now(datetime.timezone.utc)

    step("Communes (geo.api.gouv.fr)", 5)
    try:
        items = geoapi.communes(cfg, live=live)
        store.upsert_communes(items, f"geo.api.gouv.fr ({items[0]['origin'] if items else '?'})", cfg)
        report.append({"dataset": "Communes et contours", "ok": True, "rows": len(items), "origin": items[0]["origin"] if items else None})
    except Exception as exc:
        report.append({"dataset": "Communes et contours", "ok": False, "error": str(exc)[:200]})
    codes = [c["code"] for c in store.communes(cfg)]

    step("Statistiques INSEE et Éducation nationale", 15)
    rows, ind_report = indicators.fetch_all(codes, cfg, live=live,
                                            progress=lambda label, ok, msg: step(f"{label} : {msg}", 30))
    store.replace_indicators(rows, cfg)
    report += ind_report

    step("Écoles, collèges, lycées (annuaire de l'Éducation nationale)", 70)
    try:
        schools = school_equipments(cfg, live)
        result = store.upsert_equipments(schools, "education_nationale", actor, cfg)
        report.append({"dataset": "Établissements scolaires", "ok": not result["deletion_held"], "rows": len(schools), **result,
                       **({"error": f"{result['deletion_held']} suppressions retenues (réponse suspecte)"} if result["deletion_held"] else {})})
    except Exception as exc:
        report.append({"dataset": "Établissements scolaires", "ok": False, "error": str(exc)[:200]})

    step("Établissements de santé (FINESS)", 78)
    health: List[Dict[str, Any]] = []
    try:
        health = finess_equipments(cfg, live)
        result = store.upsert_equipments(health, "finess", actor, cfg)
        report.append({"dataset": "Établissements de santé (FINESS)", "ok": not result["deletion_held"], "rows": len(health), **result})
    except Exception as exc:
        report.append({"dataset": "Établissements de santé (FINESS)", "ok": False, "error": str(exc)[:200]})

    step("Santé, eau, commerces, transport, services (OpenStreetMap)", 85)
    try:
        facilities = osm_equipments(cfg, live, official_health=health)
        result = store.upsert_equipments(facilities, "openstreetmap", actor, cfg)
        report.append({"dataset": "Équipements du quotidien (OpenStreetMap)", "ok": not result["deletion_held"], "rows": len(facilities),
                       **result, **({"error": f"{result['deletion_held']} suppressions retenues (réponse suspecte)"} if result["deletion_held"] else {})})
    except Exception as exc:
        report.append({"dataset": "Équipements du quotidien (OpenStreetMap)", "ok": False, "error": str(exc)[:200]})

    failed = [r["dataset"] for r in report if not r["ok"]]
    summary = {"started_at": started.isoformat(), "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "report": report, "failed": failed, "live": live}
    audit.record("data.sync", actor=actor, target="open-data", outcome="success" if not failed else "partial",
                 details={"failed": failed, "datasets": len(report)}, settings=cfg)
    notify.notify_event(
        "donnees", "Synchronisation des données ouvertes " + ("terminée" if not failed else "partielle"),
        level="success" if not failed else "warning",
        details={"Jeux de données": len(report), "En échec": ", ".join(failed) or "aucun", "Par": actor},
        view="donnees", label="Sources et fraîcheur", settings=cfg,
    )
    step("Terminé", 100)
    return summary


# --------------------------------------------------------------------------- offline snapshot


def export_snapshot(path: Path = SNAPSHOT, settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Write the current statistics and open-data facilities to the bundled snapshot."""
    from app.db import read_db

    cfg = settings or get_settings()
    with read_db(cfg) as conn:
        ind = [list(r) for r in conn.execute("SELECT geo, indicator, year, value, source, retrieved_at FROM indicators").fetchall()]
        eq = [dict(r) for r in conn.execute(
            "SELECT uid, category, subtype, name, commune_code, lat, lon, capacity, capacity_unit, source, attributes "
            "FROM equipments WHERE source != 'saisie'").fetchall()]
        # Analysed communes travel too (200 m aggregated layers only: nothing finer exists).
        grid = [dict(r) for r in conn.execute(
            "SELECT commune_code, layer, computed_at, meta, payload FROM grid_layers").fetchall()]
    payload = {"created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "indicators": ind, "equipments": eq,
               "grid_layers": grid,
               "note": "Copie des données ouvertes (INSEE Melodi, Éducation nationale, OpenStreetMap) et des analyses "
                       "satellitaires agrégées à 200 m, pour un démarrage hors ligne."}
    blob = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), 9)
    path.write_bytes(blob)
    # Integrity sidecar: the snapshot is refused at load time if it does not match.
    digest_path(path).write_text(f"{hashlib.sha256(blob).hexdigest()}  {path.name}\n", encoding="ascii")
    return {"indicators": len(ind), "equipments": len(eq), "grid_layers": len(grid), "path": str(path),
            "bytes": path.stat().st_size}


def load_snapshot_if_empty(settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    """First start without data: load the bundled snapshot (statistics + facilities)."""
    from app.db import read_db

    cfg = settings or get_settings()
    with read_db(cfg) as conn:
        if conn.execute("SELECT COUNT(*) FROM indicators").fetchone()[0]:
            return None
    if not SNAPSHOT.is_file():
        return None
    blob = SNAPSHOT.read_bytes()
    expected = digest_path(SNAPSHOT).read_text(encoding="ascii").split()[0] if digest_path(SNAPSHOT).is_file() else None
    actual = hashlib.sha256(blob).hexdigest()
    if expected != actual:
        logger.error("Offline snapshot refused: SHA-256 %s does not match %s (file altered or sidecar missing)", actual, expected)
        from app.core import audit

        audit.record("data.snapshot", actor="system", target=SNAPSHOT.name, outcome="failure",
                     details={"sha256": actual, "expected": expected}, settings=cfg)
        return None
    try:
        payload = json.loads(gzip.decompress(blob))
    except Exception as exc:
        logger.warning("Bundled snapshot unreadable: %s", exc)
        return None
    store.replace_indicators([(g, i, y, v, s) for g, i, y, v, s, _at in payload.get("indicators", [])], cfg)
    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for e in payload.get("equipments", []):
        e = dict(e)
        e["commune"] = e.pop("commune_code", None)
        e["attributes"] = json.loads(e.get("attributes") or "{}")
        by_source.setdefault(e.pop("source"), []).append(e)
    for source, items in by_source.items():
        store.upsert_equipments(items, source, "snapshot", cfg)
    from app.db import db

    with db(cfg) as conn:
        for layer in payload.get("grid_layers", []):
            conn.execute(
                "INSERT INTO grid_layers (commune_code, layer, computed_at, meta, payload) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(commune_code, layer) DO NOTHING",
                (layer["commune_code"], layer["layer"], layer["computed_at"], layer["meta"], layer["payload"]),
            )
    logger.info("Offline snapshot of %s loaded (%s values)", payload.get("created_at"), len(payload.get("indicators", [])))
    from app.core import audit

    audit.record("data.snapshot", actor="system", target=SNAPSHOT.name,
                 details={"sha256": actual, "created_at": payload.get("created_at")}, settings=cfg)
    return {"created_at": payload.get("created_at"), "indicators": len(payload.get("indicators", []))}
