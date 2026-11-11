"""Satellite analyses and the 200 m grid layers (atlas), cell dossiers, watch, census scout list.

Grid layers travel in a compact form — ``{"grid": {...}, "fields": [...], "cells": [[row, col, v1, …]]}`` —
the console rebuilds the 200 m squares from the grid constants (a few hundred kB instead
of megabytes of GeoJSON). No layer finer than 200 m exists anywhere in the API.
"""

from __future__ import annotations

import csv
import io
import math
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.analyse import access, builtup, grid, jobs, layers as layer_store, population, privacy, watch
from app.api.deps import analyst, viewer
from app.config import get_settings
from app.core import audit
from app.territoire import store

router = APIRouter(tags=["analyses"])
CODE = Path(..., pattern=r"^\d{5}$")
LAYERS = {
    "bati": "Part bâtie du carreau",
    "croissance": "Surface bâtie gagnée (ha)",
    "population": "Habitants estimés",
    "enfants": "Enfants de 3 à 10 ans estimés",
    "acces": "Distance à l'équipement le plus proche (m)",
    "batiments": "Bâtiments (empreintes Microsoft)",
    "eau": "Plan d'eau (part du carreau)",
}


class AnalysisRequest(BaseModel):
    kind: str = "commune"
    commune: str
    sentinel2: bool = True


def _grid_info() -> Dict[str, float]:
    return {"lat0": grid.LAT0, "lon0": grid.LON0, "dlat": grid.DLAT, "dlon": grid.DLON, "cell_m": grid.CELL_M}


def _compact(values: Dict[str, Any], fields: List[str]) -> List[List[Any]]:
    out = []
    for cid, v in values.items():
        row, col = grid.parse_cell(cid)
        out.append([row, col, *(v if isinstance(v, list) else [v])])
    return out


def _commune_or_404(code: str) -> Dict[str, Any]:
    c = store.commune(code)
    if c is None:
        raise HTTPException(status_code=404, detail="Commune inconnue")
    return c


# --------------------------------------------------------------------------- jobs


@router.post("/analyses")
def start_analysis(body: AnalysisRequest, user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    cfg = get_settings()
    if body.kind != "commune":
        raise HTTPException(status_code=422, detail="Type d'analyse inconnu")
    _commune_or_404(body.commune)
    job = jobs.create("commune", body.commune, {"sentinel2": body.sentinel2}, user["username"], cfg)
    if job["created"]:
        jobs.dispatch(job, cfg)
    return {"job": job}


@router.get("/analyses")
def list_analyses(commune: Optional[str] = Query(None, pattern=r"^\d{3,5}$"), _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    return {"jobs": jobs.recent(commune, 50), "kinds": jobs.KINDS}


@router.get("/analyses/{job_id}")
def get_analysis(job_id: int, _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable")
    return {"job": job}


# --------------------------------------------------------------------------- grid layers


@router.get("/grille/{code}/meta")
def grid_meta(code: str = CODE, _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """What has been computed for a commune: years, calibration quality, totals, constraints."""
    _commune_or_404(code)
    from app.analyse import satellite

    inventory = layer_store.inventory(code)
    built = inventory.get("builtup")
    if built:
        built["meta"]["quality"] = satellite.grade(built["meta"].get("calibration"))
    return {
        "analysed": built is not None, "computed_at": built["computed_at"] if built else None,
        "builtup": built["meta"] if built else None,
        "layers": {k: {"computed_at": v["computed_at"], **{m: v["meta"].get(m) for m in ("source", "cells", "areas") if m in v["meta"]}}
                   for k, v in inventory.items() if k != "builtup"},
        "population": population.totals_by_year(code) if built else None,
        "grid": _grid_info(), "layer_labels": LAYERS, "categories": store.CATEGORIES,
    }


@router.get("/grille/{code}/couche")
def grid_layer(code: str = CODE, layer: str = Query("bati"), year: Optional[int] = Query(None, ge=1985, le=2100),
               since: int = Query(2019, ge=1985, le=2100), category: str = Query("ecole"),
               hypothese: bool = Query(False), _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """One layer of the 200 m grid for a commune, compact form."""
    if layer not in LAYERS:
        raise HTTPException(status_code=422, detail="Couche inconnue")
    _commune_or_404(code)
    cfg = get_settings()
    base = {"grid": _grid_info(), "layer": layer, "label": LAYERS[layer],
            "secrecy": {"min_buildings": cfg.privacy_min_buildings, "below": privacy.BELOW}}
    data = builtup.load(code, cfg)
    stored_buildings = layer_store.load(code, "buildings")
    buildings = stored_buildings[0] if stored_buildings else None
    latest = builtup.year_values(data, max(data["years"])) if data else {}
    sparse = privacy.sparse_cells(latest, buildings, data["meta"] if data else None, cfg)
    if layer == "eau":
        stored = layer_store.load(code, "water")
        if stored is None:
            return {**base, "available": False, "cells": []}
        return {**base, "available": True, "fields": ["value"], "cells": _compact(stored[0], ["value"]), "meta": stored[1]}
    if layer == "batiments":
        if buildings is None:
            return {**base, "available": False, "cells": []}
        values = {cid: privacy.generalise_count(v[0] if isinstance(v, list) else v, cfg) for cid, v in buildings.items()}
        return {**base, "available": True, "fields": ["value"], "cells": _compact(values, ["value"]), "meta": stored_buildings[1]}
    if data is None:
        return {**base, "available": False, "cells": [], "reason": "Analyse du bâti non réalisée pour cette commune."}
    year = builtup.nearest_year(data["years"], year or max(data["years"]))
    if layer == "bati":
        values = {cid: (privacy.generalise_share(v) if cid in sparse else v) for cid, v in builtup.year_values(data, year).items()}
        return {**base, "available": True, "year": year, "years": data["years"], "fields": ["value"], "cells": _compact(values, ["value"])}
    if layer == "croissance":
        since_y = builtup.nearest_year(data["years"], since)
        floor = privacy.min_growth_ha(data["meta"], cfg)
        values = {cid: v for cid, v in builtup.growth(data, since_y, year).items() if abs(v) >= floor}
        return {**base, "available": True, "year": year, "since": since_y, "years": data["years"], "fields": ["value"],
                "cells": _compact(values, ["value"]), "growth_floor_ha": floor}
    pop = population.model(code, year, cfg, use_hypothesis=hypothese)
    if layer in ("population", "enfants"):
        key = "pop" if layer == "population" else "enfants_3_10"
        values = {cid: (privacy.BELOW if cid in sparse else privacy.round_people(v[key])) for cid, v in pop["cells"].items()}
        return {**base, "available": True, "year": pop["year"], "years": data["years"], "fields": ["value"],
                "cells": _compact(values, ["value"]), "model": {k: pop[k] for k in ("total", "children_3_10", "density_per_built_ha",
                                                                                    "calibration", "extrapolated", "method", "hypothesis")}}
    if category not in store.CATEGORIES:
        raise HTTPException(status_code=422, detail="Catégorie inconnue")
    acc = access.accessibility(code, category, year, cfg, use_hypothesis=hypothese, pop=pop)
    values = {cid: [c["distance_m"] if c["distance_m"] is not None else -1,
                    privacy.BELOW if cid in sparse else privacy.round_people(c["demand"])] for cid, c in acc["cells"].items()}
    return {**base, "available": True, "year": acc["year"], "years": data["years"], "fields": ["distance_m", "demand"],
            "cells": _compact(values, ["distance_m", "demand"]), "stats": acc["stats"], "radius_m": acc["radius_m"],
            "radius_trip_m": acc["radius_trip_m"], "detour_factor": acc["detour_factor"],
            "category": category, "facilities": acc["facilities"], "population": acc["population"]}


@router.get("/grille/{code}/carreau/{cell}")
def cell_dossier(code: str = CODE, cell: str = Path(..., pattern=r"^-?\d{1,5}_-?\d{1,5}$"),
                 _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """Everything known about one 200 m cell: built series, estimated population, nearest facilities."""
    commune = _commune_or_404(code)
    cfg = get_settings()
    row, col = grid.parse_cell(cell)
    lon, lat = grid.cell_center(row, col)
    data = builtup.load(code, cfg)
    out: Dict[str, Any] = {"cell": cell, "lat": round(lat, 6), "lon": round(lon, 6), "commune": commune["nom"],
                           "bounds": grid.cell_bounds(row, col), "cell_m": grid.CELL_M}
    buildings = layer_store.load(code, "buildings", cfg)
    sparse = False
    if data is not None:
        latest = builtup.year_values(data, max(data["years"]))
        sparse = cell in privacy.sparse_cells({cell: latest.get(cell, 0.0)},
                                               {cell: buildings[0][cell]} if buildings and cell in buildings[0] else None,
                                               data["meta"], cfg)
        series = data["cells"].get(cell)
        shown = [(privacy.generalise_share(v) if sparse else v) for v in (series or [0.0] * len(data["years"]))]
        out["built_series"] = [{"year": y, "fraction": shown[n], "ha": round(shown[n] * grid.CELL_HA, 2)}
                               for n, y in enumerate(data["years"])]
        last = max(data["years"])
        pop = population.model(code, last, cfg)
        cell_pop = pop["cells"].get(cell)
        if cell_pop and not sparse:
            out["population"] = {k: privacy.round_people(v) for k, v in cell_pop.items()}
        out["population_year"] = pop.get("year")
        out["population_method"] = pop.get("method")
    if buildings is not None and cell in buildings[0]:
        count = buildings[0][cell][0]
        out["buildings"] = {"count": privacy.generalise_count(count, cfg),
                            "source": "Microsoft Global ML Building Footprints (comptage agrégé)"}
    out["sparse"] = sparse
    out["secrecy"] = {"min_buildings": cfg.privacy_min_buildings,
                      "note": f"Carreau peu bâti (moins de {cfg.privacy_min_buildings} bâtiments) : effectifs non affichés, "
                              "part bâtie arrondie à 5 % (secret statistique)." if sparse else ""}
    near: Dict[str, Any] = {}
    west, south, east, north = commune["bbox"]
    import numpy as np

    # One query for every family (existing and provisional facilities, as the accessibility layer).
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for item in store.equipments(bbox=(west - 0.09, south - 0.09, east + 0.09, north + 0.09),
                                 statuses=("existant", "provisoire"), settings=cfg):
        by_category.setdefault(item["category"], []).append(item)
    for cat, meta in store.CATEGORIES.items():
        items = by_category.get(cat)
        if not items:
            near[cat] = None
            continue
        d = grid.haversine_m(lon, lat, np.array([i["lon"] for i in items]), np.array([i["lat"] for i in items]))
        k = int(np.argmin(d))
        radius = access.radius_for(cat, cfg)
        walk = float(d[k]) * max(cfg.detour_factor, 1.0)
        # Same rule as the accessibility layer: the estimated trip is compared with the radius.
        near[cat] = {"label": meta["label"], "name": items[k]["name"], "distance_m": round(float(d[k])),
                     "walk_m": round(walk), "covered": bool(walk <= radius), "radius_m": radius,
                     "status": items[k]["status"]}
    out["nearest"] = near
    return out


@router.get("/grille/{code}/veille")
def watch_hotspots(code: str = CODE, since: int = Query(2019, ge=1985, le=2100), _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    _commune_or_404(code)
    result = watch.hotspots(code, get_settings(), since=since, notify=False)
    for cluster in result.get("clusters", []):
        cluster["cells"] = [list(grid.parse_cell(c)) for c in cluster.pop("cell_ids")]
    return {**result, "grid": _grid_info()}


@router.get("/grille/{code}/recensement")
def census_scout(code: str = CODE, since: int = Query(2019, ge=1985, le=2100), format: str = Query("json", pattern="^(json|csv)$"),
                 user: Dict[str, Any] = Depends(analyst)) -> Any:
    """Census scout list (aggregated cells, secrecy rule). The CSV export is audited."""
    commune = _commune_or_404(code)
    result = watch.census_scout(code, since, get_settings())
    if not result.get("available"):
        raise HTTPException(status_code=409, detail="Analyse du bâti non réalisée pour cette commune")
    if format == "json":
        return result
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([f"# Recensement Éclaireur — {commune['nom']} ({code}) — croissance du bâti {result['since']} → {result['until']}"])
    writer.writerow([f"# {result['notice']}"])
    writer.writerow(["carreau_200m", "latitude_centre", "longitude_centre", "bati_gagne_ha", "batiments_estimes", "part_batie_actuelle"])
    for r in result["rows"]:
        writer.writerow([r["cell"], r["lat"], r["lon"], str(r["growth_ha"]).replace(".", ","), r["new_buildings_est"],
                         str(r["built_share_now"]).replace(".", ",")])
    writer.writerow([f"# Autres carreaux (non listés, règle de secret) : {result['hidden']['cells']} carreaux, "
                     f"{result['hidden']['growth_ha']} ha"])
    audit.record("export.census", actor=user["username"], target=f"commune:{code}",
                 details={"since": result["since"], "until": result["until"], "rows": len(result["rows"])})
    filename = f"recensement-eclaireur-{code}-{result['since']}-{result['until']}.csv"
    return Response(content=buffer.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/grille/{code}/contraintes")
def constraints(code: str = CODE, _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """Protected areas (WDPA) and road cells used by the siting constraints."""
    _commune_or_404(code)
    protected = layer_store.load(code, "protected")
    roads = layer_store.load(code, "roads")
    return {"protected": {"type": "FeatureCollection", "features": protected[0] if protected else []},
            "road_cells": [list(grid.parse_cell(c)) for c in (roads[0] if roads else [])], "grid": _grid_info()}


# --------------------------------------------------------------------------- visual validation


class VerdictBody(BaseModel):
    cell: str = Field(..., max_length=13)
    year: int = Field(..., ge=1985, le=2100)
    verdict: str = Field(..., max_length=20)
    imagery: str = Field("", max_length=80)


@router.get("/validation/{code}")
def validation_sample(code: str = CODE, year: Optional[int] = Query(None, ge=1985, le=2100),
                      user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """Stratified sample of cells to check on imagery, with the verdicts already given and the agreement."""
    from app.analyse import validation

    _commune_or_404(code)
    data = builtup.load(code)
    if data is None:
        raise HTTPException(status_code=409, detail="Analyse du bâti non réalisée pour cette commune")
    year = builtup.nearest_year(data["years"], year or max(data["years"]))
    report = validation.report(code, year)
    mine = {e["cell"]: e["verdict"] for e in report["entries"] if e["created_by"] == user["username"]}
    cells = validation.sample(code, year)
    for c in cells:
        c["my_verdict"] = mine.get(c["cell"])
        if not c["my_verdict"]:
            c.pop("predicted_share")  # blind control: the platform's answer is revealed after the vote
    # Blind for every controller: the verdicts of the others must not reveal the platform's answer
    # (their "predicted" share) on a cell this person has not judged yet.
    report["entries"] = [e if e["cell"] in mine else {k: v for k, v in e.items() if k != "predicted"} for e in report["entries"]]
    return {"year": year, "years": data["years"], "cells": cells, "report": report,
            "verdicts": validation.VERDICTS, "grid": _grid_info()}


@router.post("/validation/{code}")
def validation_record(body: VerdictBody, code: str = CODE, user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    from app.analyse import validation

    _commune_or_404(code)
    if not re.fullmatch(r"-?\d{1,5}_-?\d{1,5}", body.cell):
        raise HTTPException(status_code=422, detail="Carreau invalide")
    try:
        validation.record(code, body.cell, body.year, body.verdict, body.imagery, user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    data = builtup.load(code)
    if data is None:
        raise HTTPException(status_code=409, detail="Analyse du bâti non réalisée pour cette commune")
    year = builtup.nearest_year(data["years"], body.year)  # the verdict was stored for this year
    predicted = builtup.year_values(data, year).get(body.cell, 0.0)
    report = validation.report(code, year)
    judged = {e["cell"] for e in report["entries"] if e["created_by"] == user["username"]}
    report["entries"] = [e if e["cell"] in judged else {k: v for k, v in e.items() if k != "predicted"} for e in report["entries"]]
    return {"report": report, "predicted_share": round(predicted, 3)}
