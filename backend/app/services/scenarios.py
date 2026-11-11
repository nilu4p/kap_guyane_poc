"""Siting scenarios: candidate locations of new facilities, saved, compared and validated."""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional

from app.config import Settings, get_settings
from app.core import audit
from app.db import db, read_db, row, rows

STATUSES = {"brouillon": "Brouillon", "valide": "Validé", "archive": "Archivé"}
MAX_SITES = 20


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _decode(r: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if r is None:
        return None
    r = dict(r)
    for key in ("sites", "params", "evaluation"):
        r[key] = json.loads(r.get(key) or ("[]" if key == "sites" else "{}"))
    r["status_label"] = STATUSES.get(r["status"], r["status"])
    return r


def _clean_sites(sites: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(sites) > MAX_SITES:
        raise ValueError(f"{MAX_SITES} sites au plus par scénario")
    out = []
    for s in sites:
        lat, lon = float(s["lat"]), float(s["lon"])
        if not (1.5 <= lat <= 6.5 and -55.5 <= lon <= -51.0):
            raise ValueError("Site hors de la Guyane")
        out.append({"lat": round(lat, 6), "lon": round(lon, 6), "name": str(s.get("name") or "")[:120],
                    "capacity": float(s["capacity"]) if s.get("capacity") not in (None, "") else None})
    return out


def get(scenario_id: int, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    with read_db(settings) as conn:
        return _decode(row(conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()))


def list_scenarios(commune: Optional[str] = None, settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    query, params = "SELECT * FROM scenarios", []
    if commune:
        query += " WHERE commune_code = ?"
        params.append(commune)
    with read_db(settings) as conn:
        return [_decode(r) for r in rows(conn.execute(query + " ORDER BY updated_at DESC", params).fetchall())]  # type: ignore[misc]


def save(data: Dict[str, Any], actor: str, scenario_id: Optional[int] = None, settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Create or update a scenario; its evaluation (coverage before / after) is recomputed and stored."""
    from app.analyse import access
    from app.territoire import store

    cfg = settings or get_settings()
    if data["category"] not in store.CATEGORIES:
        raise ValueError("Catégorie inconnue")
    if store.commune(data["commune_code"], cfg) is None:
        raise ValueError("Commune inconnue")
    sites = _clean_sites(data.get("sites") or [])
    params = {"use_hypothesis": bool((data.get("params") or {}).get("use_hypothesis")),
              **{k: v for k, v in (data.get("params") or {}).items() if k in ("k", "radius_m", "constraints", "year")}}
    evaluation = access.evaluate(data["commune_code"], data["category"], sites, settings=cfg,
                                 use_hypothesis=params["use_hypothesis"]) if sites else {}
    stored_eval = {k: evaluation.get(k) for k in ("year", "radius_m", "before", "after", "gain")} if evaluation.get("available") else {}
    now = _now()
    with db(cfg) as conn:
        if scenario_id is None:
            scenario_id = int(conn.execute(
                "INSERT INTO scenarios (commune_code, category, name, description, sites, params, evaluation, status, created_at, "
                "created_by, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, 'brouillon', ?, ?, ?, ?) RETURNING id",
                (data["commune_code"], data["category"], str(data["name"])[:160], str(data.get("description") or "")[:4000],
                 json.dumps(sites), json.dumps(params), json.dumps(stored_eval), now, actor, now, actor),
            ).fetchone()[0])
        else:
            current = conn.execute("SELECT status FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
            if current is None:
                raise LookupError("Scénario introuvable")
            if current["status"] == "valide":
                raise PermissionError("Un scénario validé ne se modifie plus : dupliquez-le")
            conn.execute(
                "UPDATE scenarios SET name = ?, description = ?, sites = ?, params = ?, evaluation = ?, updated_at = ?, updated_by = ? "
                "WHERE id = ?",
                (str(data["name"])[:160], str(data.get("description") or "")[:4000], json.dumps(sites), json.dumps(params),
                 json.dumps(stored_eval), now, actor, scenario_id),
            )
    audit.record("scenario.save", actor=actor, target=f"scenario:{scenario_id}",
                 details={"commune": data["commune_code"], "category": data["category"], "sites": len(sites)}, settings=cfg)
    out = get(scenario_id, cfg)
    assert out is not None
    return out


def set_status(scenario_id: int, status: str, actor: str, settings: Optional[Settings] = None) -> Dict[str, Any]:
    cfg = settings or get_settings()
    if status not in STATUSES:
        raise ValueError("Statut inconnu")
    current = get(scenario_id, cfg)
    if current is None:
        raise LookupError("Scénario introuvable")
    frozen = None
    if status == "valide" and current["status"] != "valide":
        # Validation freezes the figures: the signed file will quote exactly what was validated,
        # whatever the later data updates (new census, new satellite season, new facilities).
        from app.analyse import access, layers as layer_store

        evaluation = access.evaluate(current["commune_code"], current["category"], current["sites"], settings=cfg,
                                     use_hypothesis=bool(current["params"].get("use_hypothesis")))
        if not evaluation.get("available"):
            raise ValueError(evaluation.get("reason") or "Évaluation impossible : scénario non validable")
        inventory = layer_store.inventory(current["commune_code"], cfg)
        frozen = {**evaluation, "frozen_at": _now(), "frozen_by": actor,
                  "basis": {"analysis_computed_at": (inventory.get("builtup") or {}).get("computed_at"),
                            "population": evaluation["population"].get("calibration")}}
    with db(cfg) as conn:
        if frozen is not None:
            conn.execute("UPDATE scenarios SET status = ?, evaluation = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                         (status, json.dumps(frozen, default=str), _now(), actor, scenario_id))
        else:
            conn.execute("UPDATE scenarios SET status = ?, updated_at = ?, updated_by = ? WHERE id = ?", (status, _now(), actor, scenario_id))
    audit.record("scenario.status", actor=actor, target=f"scenario:{scenario_id}", details={"status": status}, settings=cfg)
    scenario = get(scenario_id, cfg)
    assert scenario is not None
    if status == "valide":
        from app.services import notify

        notify.notify_event("decisions", f"Scénario validé — {scenario['name']}", level="success",
                            details={"Commune": scenario["commune_code"], "Sites": len(scenario["sites"]), "Par": actor},
                            view=f"decision/{scenario['commune_code']}", label="Aide à la décision", settings=cfg)
    return scenario


def delete(scenario_id: int, actor: str, settings: Optional[Settings] = None) -> None:
    cfg = settings or get_settings()
    with db(cfg) as conn:
        current = conn.execute("SELECT status FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
        if current is None:
            raise LookupError("Scénario introuvable")
        if current["status"] == "valide":
            raise PermissionError("Un scénario validé s'archive, il ne se supprime pas")
        conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
    audit.record("scenario.delete", actor=actor, target=f"scenario:{scenario_id}", settings=cfg)
