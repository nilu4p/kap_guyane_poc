"""Territory: communes, statistics, indicators catalogue, population hypotheses, open-data sync."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.api.deps import analyst, supervisor, viewer
from app.config import get_settings
from app.core import audit
from app.core.geo import simplify_geometry
from app.territoire import profile, store

router = APIRouter(tags=["territoire"])
CODE = Path(..., pattern=r"^\d{5}$")


class Hypothesis(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    value: int = Field(..., ge=1, le=2_000_000)
    low: Optional[int] = Field(None, ge=1, le=2_000_000)
    high: Optional[int] = Field(None, ge=1, le=2_000_000)
    source: str = Field("", max_length=300)
    note: str = Field("", max_length=1000)


@router.get("/communes")
def list_communes(geometry: bool = Query(False), _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """The 22 communes (simplified contours on request, for the overview map)."""
    from app.analyse import layers as layer_store

    items = store.communes(with_contour=geometry)
    analysed = layer_store.analysed_communes()
    for c in items:
        if geometry:
            c["contour"] = simplify_geometry(c["contour"], 0.004)
        c["analysed_at"] = analysed.get(c["code"])
    return {"communes": items, "default": get_settings().default_commune}


@router.get("/territoire/kpis")
def territory_kpis(_user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """Every KPI of every commune + Guyane (comparison table, choropleth map)."""
    table = profile.kpi_table()
    return {"kpis": profile.describe_kpis(), "themes": profile.THEMES, "values": table["values"],
            "communes": [{k: c[k] for k in ("code", "nom", "epci", "population")} for c in table["communes"]],
            "department": table["department"]}


@router.get("/communes/{code}")
def commune_profile(code: str = CODE, _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    result = profile.profile(code)
    if result is None:
        raise HTTPException(status_code=404, detail="Commune inconnue")
    return result


@router.get("/communes/{code}/contour")
def commune_contour(code: str = CODE, _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    c = store.commune(code)
    if c is None:
        raise HTTPException(status_code=404, detail="Commune inconnue")
    return {"type": "Feature", "geometry": simplify_geometry(c["contour"], 0.0007),
            "properties": {"code": c["code"], "nom": c["nom"], "bbox": c["bbox"]}}


@router.put("/communes/{code}/hypothese")
def put_hypothesis(body: Hypothesis, code: str = CODE, user: Dict[str, Any] = Depends(supervisor)) -> Dict[str, Any]:
    """The commune's own population figure, kept next to (never instead of) the INSEE legal population."""
    if store.commune(code) is None:
        raise HTTPException(status_code=404, detail="Commune inconnue")
    if body.low and body.high and body.low > body.high:
        raise HTTPException(status_code=422, detail="Fourchette incohérente")
    store.set_hypothesis(code, body.model_dump(), user["username"])
    audit.record("territory.hypothesis", actor=user["username"], target=f"commune:{code}", details=body.model_dump())
    return {"hypothesis": store.hypothesis(code)}


@router.delete("/communes/{code}/hypothese")
def delete_hypothesis(code: str = CODE, user: Dict[str, Any] = Depends(supervisor)) -> Dict[str, Any]:
    if store.commune(code) is None:
        raise HTTPException(status_code=404, detail="Commune inconnue")
    store.set_hypothesis(code, None, user["username"])
    audit.record("territory.hypothesis", actor=user["username"], target=f"commune:{code}", details={"removed": True})
    return {"hypothesis": None}


@router.get("/donnees")
def data_status(_user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """Freshness of every statistical source and the last synchronisations."""
    from app.analyse import jobs
    from app.territoire.indicators import SOURCES

    cfg = get_settings()
    fresh = store.data_freshness(cfg)
    return {"sources": [{"id": k, "label": SOURCES.get(k, k), **v} for k, v in sorted(fresh.items())],
            "syncs": [j for j in jobs.recent(cfg.department_code, 10, cfg) if j["kind"] == "sync"],
            "refresh_days": cfg.data_refresh_days}


@router.post("/donnees/sync")
def start_sync(user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    from app.analyse import jobs

    cfg = get_settings()
    job = jobs.create("sync", cfg.department_code, {}, user["username"], cfg)
    if job["created"]:
        jobs.dispatch(job, cfg)
    return {"job": job}
