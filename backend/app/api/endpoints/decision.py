"""Decision support: siting recommendations, scenario evaluation and register."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.analyse import access
from app.api.deps import analyst, supervisor, viewer
from app.config import get_settings
from app.core import audit
from app.services import scenarios
from app.territoire import store

router = APIRouter(tags=["decision"])


class Constraints(BaseModel):
    exclude_water: bool = True
    max_built_fraction: float = Field(0.6, ge=0.0, le=1.0)
    road_max_m: Optional[float] = Field(500.0, ge=0, le=20000)
    exclude_protected: bool = False
    min_spacing_m: Optional[float] = Field(None, ge=0, le=60000)


class SitingRequest(BaseModel):
    commune: str = Field(..., pattern=r"^\d{5}$")
    category: str
    k: int = Field(3, ge=1, le=10)
    radius_m: Optional[float] = Field(None, ge=100, le=60000)
    year: Optional[int] = Field(None, ge=2016, le=2100)
    use_hypothesis: bool = False
    include_planned: bool = True
    constraints: Constraints = Constraints()


class Site(BaseModel):
    lat: float = Field(..., ge=1.5, le=6.5)
    lon: float = Field(..., ge=-55.5, le=-51.0)
    name: str = Field("", max_length=120)
    capacity: Optional[float] = Field(None, ge=0, le=100000)


class EvaluateRequest(BaseModel):
    commune: str = Field(..., pattern=r"^\d{5}$")
    category: str
    sites: List[Site] = Field(..., max_length=20)
    year: Optional[int] = Field(None, ge=2016, le=2100)
    use_hypothesis: bool = False


class ScenarioBody(BaseModel):
    commune_code: str = Field(..., pattern=r"^\d{5}$")
    category: str
    name: str = Field(..., min_length=1, max_length=160)
    description: str = Field("", max_length=4000)
    sites: List[Site] = Field(default_factory=list, max_length=20)
    params: Dict[str, Any] = Field(default_factory=dict)


class StatusBody(BaseModel):
    status: str


def _category(category: str) -> None:
    if category not in store.CATEGORIES:
        raise HTTPException(status_code=422, detail="Catégorie inconnue")


# Plain (sync) endpoints: FastAPI runs them in its thread pool. Their database reads and audit
# writes must never run on the event loop, where they would stall every other request.


@router.post("/decision/implantation")
def recommend(body: SitingRequest, user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """Where to put ``k`` new facilities of a family (greedy maximal covering, under constraints)."""
    _category(body.category)
    try:
        result = access.site(body.commune, body.category, body.k, body.year, body.constraints.model_dump(), body.radius_m,
                             get_settings(), body.use_hypothesis, body.include_planned)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit.record("decision.siting", actor=user["username"], target=f"commune:{body.commune}",
                 details={"category": body.category, "k": body.k, "sites": len(result.get("sites") or [])})
    return result


@router.post("/decision/evaluer")
def evaluate(body: EvaluateRequest, _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """Coverage before / after a set of sites drawn on the map."""
    _category(body.category)
    try:
        return access.evaluate(body.commune, body.category, [s.model_dump() for s in body.sites], body.year, get_settings(),
                               body.use_hypothesis)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/decision/acces")
def coverage(commune: str = Query(..., pattern=r"^\d{5}$"), year: Optional[int] = Query(None, ge=2016, le=2100),
             hypothese: bool = Query(False), _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """Coverage statistics of every facility family for a commune (dashboard)."""
    from app.analyse import builtup, population

    cfg = get_settings()
    data = builtup.load(commune, cfg)
    if data is None:
        return {"available": False}
    year = year or max(data["years"])
    pop = population.model(commune, year, cfg, use_hypothesis=hypothese)
    out = {}
    for cat in store.CATEGORIES:
        try:
            acc = access.accessibility(commune, cat, year, cfg, use_hypothesis=hypothese, pop=pop)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if acc.get("available"):
            out[cat] = {**acc["stats"], "radius_m": acc["radius_trip_m"], "label": acc["label"], "demand": acc["demand"]}
    return {"available": True, "year": year, "families": out,
            "population": {k: pop[k] for k in ("total", "children_3_10", "calibration", "extrapolated", "method")}}


@router.get("/scenarios")
def list_scenarios(commune: Optional[str] = Query(None, pattern=r"^\d{5}$"), _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    return {"scenarios": scenarios.list_scenarios(commune), "statuses": scenarios.STATUSES}


@router.post("/scenarios")
def create_scenario(body: ScenarioBody, user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    _category(body.category)
    try:
        return {"scenario": scenarios.save({**body.model_dump(), "sites": [s.model_dump() for s in body.sites]}, user["username"])}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/scenarios/{scenario_id}")
def update_scenario(scenario_id: int, body: ScenarioBody, user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    _category(body.category)
    try:
        return {"scenario": scenarios.save({**body.model_dump(), "sites": [s.model_dump() for s in body.sites]},
                                           user["username"], scenario_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/scenarios/{scenario_id}/statut")
def scenario_status(scenario_id: int, body: StatusBody, user: Dict[str, Any] = Depends(supervisor)) -> Dict[str, Any]:
    """Validate or archive a scenario (head of department)."""
    try:
        return {"scenario": scenarios.set_status(scenario_id, body.status, user["username"])}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(scenario_id: int, user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    try:
        scenarios.delete(scenario_id, user["username"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"deleted": scenario_id}
