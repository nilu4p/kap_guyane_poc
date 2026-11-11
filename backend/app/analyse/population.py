"""Where the inhabitants live: population and children spread on the 200 m grid.

**Dasymetric model** (stated with every figure, never presented as a census):

1. Census year *B* = latest INSEE legal population of the commune (``P_B``).
2. Occupancy density ``d = P_B / built hectares of the commune in year B`` (fused
   built-up layer): persons per built hectare, calibrated on the commune itself — or, in the
   communes split into IRIS by INSEE, **per district** (population of the IRIS / its built
   hectares, with the district's own age structure), the remainder of the commune forming a
   residual zone so that the commune total is preserved.
3. Persons in a cell in year *y* = ``d × built hectares of the cell in year y``.
   For years after *B* this is an **extrapolation at constant occupancy**: the
   commune total then tells how many people the measured growth of the built
   surface *could* house — an independent, reproducible indicator, not a
   counter-census (see the ethics charter).
4. An explicit **hypothesis** (e.g. the town hall's own estimate) can replace ``P_B``:
   the density is then calibrated on that figure and the hypothesis is named on
   every result.
5. Children: the census age shares of the commune (INSEE, 3-10 years ≈ ¾ of the
   2-5 band + the 6-10 band; 11-14; 15-17) applied to each cell.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.analyse import builtup, layers as layer_store
from app.analyse.grid import CELL_HA
from app.config import Settings, get_settings
from app.territoire import store


def age_shares(commune: str, settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Shares of the population by school age (latest census), commune first, department fallback."""
    cfg = settings or get_settings()
    for geo in (commune, cfg.department_code):
        series = store.series(geo, ("rp_pop_total", "rp_age_2_5", "rp_age_6_10", "rp_age_11_14", "rp_age_15_17"), cfg)
        total = series.get("rp_pop_total") or {}
        if not total:
            continue
        year = max(total)
        pop = total[year]
        if not pop:
            continue

        def share(name: str) -> float:
            return float((series.get(name) or {}).get(year, 0.0)) / pop

        return {"year": year, "geo": geo, "enfants_3_10": 0.75 * share("rp_age_2_5") + share("rp_age_6_10"),
                "enfants_11_14": share("rp_age_11_14"), "jeunes_15_17": share("rp_age_15_17")}
    return {"year": None, "geo": None, "enfants_3_10": 0.0, "enfants_11_14": 0.0, "jeunes_15_17": 0.0}


def _zone_shares(ages: Dict[str, float]) -> Dict[str, float]:
    total = ages.get("_T") or 0.0
    if not total:
        return {}
    return {"enfants_3_10": (0.75 * ages.get("Y2T5", 0.0) + ages.get("Y6T10", 0.0)) / total,
            "enfants_11_14": ages.get("Y11T14", 0.0) / total, "jeunes_15_17": ages.get("Y15T17", 0.0) / total}


def _iris_zones(commune: str, built_calib: Dict[str, float], calib_pop: float, commune_density: float,
                commune_shares: Dict[str, Any], cfg: Settings) -> Optional[Dict[str, Any]]:
    """Per-IRIS densities and age shares; None when the IRIS calibration is not usable.

    Each IRIS known to the census gets ``its population / its built hectares``; the rest of the
    commune (IRIS split since the census, or without figures) forms a residual zone with the
    remaining population. An IRIS whose density would be implausible (< ⅕ or > 5 × the commune
    density, or less than 2 built hectares) is merged into the residual zone.
    """
    stored = layer_store.load(commune, "iris", cfg)
    if stored is None or not stored[0].get("zones"):
        return None
    import numpy as np
    import shapely
    from shapely.geometry import shape

    from app.analyse.grid import cell_center, parse_cell

    cids = list(built_calib)
    if not cids:
        return None
    centers = np.array([cell_center(*parse_cell(c)) for c in cids])
    zone_of = {c: "residuel" for c in cids}
    zones: Dict[str, Dict[str, Any]] = {}
    for z in stored[0]["zones"]:
        geom = shape(z["geometry"])
        shapely.prepare(geom)
        inside = shapely.contains_xy(geom, centers[:, 0], centers[:, 1])
        members = [cids[k] for k in np.nonzero(inside)[0] if zone_of[cids[k]] == "residuel"]
        built_ha = sum(built_calib[c] for c in members) * CELL_HA
        pop = float(z["ages"].get("_T") or 0.0)
        density = pop / built_ha if built_ha > 0 else None
        if built_ha < 2.0 or density is None or not (commune_density / 5 <= density <= commune_density * 5):
            continue  # implausible: left in the residual zone
        for c in members:
            zone_of[c] = z["code"]
        zones[z["code"]] = {"nom": z["nom"], "population": pop, "built_ha": round(built_ha, 1), "density": density,
                            "shares": _zone_shares(z["ages"]) or commune_shares}
    if not zones:
        return None
    residual_pop = calib_pop - sum(z["population"] for z in zones.values())
    residual_ha = sum(built_calib[c] for c, z in zone_of.items() if z == "residuel") * CELL_HA
    if residual_pop < 0 or (residual_pop > 0 and residual_ha <= 0):
        return None  # figures inconsistent with the commune total: commune-level calibration instead
    zones["residuel"] = {"nom": "Reste de la commune", "population": residual_pop, "built_ha": round(residual_ha, 1),
                         "density": residual_pop / residual_ha if residual_ha > 0 else commune_density, "shares": commune_shares}
    return {"zone_of": zone_of, "zones": zones, "year": stored[0].get("year")}


def _calibration(commune: str, data: Dict[str, Any], cfg: Settings, use_hypothesis: bool) -> Dict[str, Any]:
    """Everything of the model that does not depend on the year shown (one computation per request)."""
    pops = store.series(commune, ("population",), cfg).get("population") or {}
    hypothesis = store.hypothesis(commune, cfg) if use_hypothesis else None
    if hypothesis:
        calib_year = int(hypothesis["year"])
        calib_pop = float(hypothesis["value"])
        basis = f"hypothèse « {hypothesis.get('source') or 'commune'} » : {int(calib_pop):,} habitants".replace(",", " ")
    elif pops:
        calib_year = max(pops)
        calib_pop = float(pops[calib_year])
        basis = f"population municipale légale INSEE {calib_year} : {int(calib_pop):,} habitants".replace(",", " ")
    else:
        calib_year, calib_pop, basis = None, None, "aucune population de référence"
    shares = age_shares(commune, cfg)
    ctx: Dict[str, Any] = {"pops": pops, "hypothesis": hypothesis, "calib_year": calib_year, "calib_pop": calib_pop,
                           "basis": basis, "shares": shares, "iris": None, "scale": 1.0}
    if calib_year is not None:
        built_ha = sum(builtup.year_values(data, calib_year).values()) * CELL_HA
        ctx["built_ha"] = built_ha
        # Infra-communal calibration (IRIS) when the census publishes it: densities and age structure by
        # district. A hypothesis scales every district by the same ratio.
        legal = float(pops[max(pops)]) if pops else None
        if legal and built_ha > 0:
            ctx["iris"] = _iris_zones(commune, builtup.year_values(data, max(pops)), legal, legal / built_ha, shares, cfg)
        ctx["scale"] = (calib_pop / legal) if (ctx["iris"] and hypothesis and legal) else 1.0
    return ctx


def model(commune: str, year: int, settings: Optional[Settings] = None, use_hypothesis: bool = False, *,
          data: Optional[Dict[str, Any]] = None, calibration: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Population (and children) per cell in ``year``, with the calibration that produced it.

    ``data`` (built-up layer) and ``calibration`` (from :func:`_calibration`) can be passed in when
    the model is evaluated for several years of the same commune.
    """
    cfg = settings or get_settings()
    data = data or builtup.load(commune, cfg)
    if data is None:
        return {"available": False, "reason": "Analyse du bâti non réalisée pour cette commune (onglet Analyses)."}
    ctx = calibration or _calibration(commune, data, cfg, use_hypothesis)
    calib_year, calib_pop, hypothesis, shares = ctx["calib_year"], ctx["calib_pop"], ctx["hypothesis"], ctx["shares"]
    # Without a reference population the calibration year is the year shown.
    built_ha = ctx["built_ha"] if calib_year is not None else sum(builtup.year_values(data, year).values()) * CELL_HA
    if calib_pop and built_ha > 0:
        density = calib_pop / built_ha
        density_origin = "calibrée sur la commune"
    else:
        density = cfg.fallback_persons_per_built_ha
        density_origin = "valeur par défaut (pas de calibration possible)"
    iris, scale = ctx["iris"], ctx["scale"]
    built_year = builtup.year_values(data, year)
    cells: Dict[str, Dict[str, float]] = {}
    total = children = 0.0
    for cid, fraction in built_year.items():
        if iris:
            zone = iris["zones"][iris["zone_of"].get(cid, "residuel")]
            d, zs = zone["density"] * scale, zone["shares"]
        else:
            d, zs = density, shares
        persons = d * fraction * CELL_HA
        if persons < 0.5:
            continue
        kids = persons * zs["enfants_3_10"]
        cells[cid] = {"pop": round(persons, 1), "enfants_3_10": round(kids, 1),
                      "enfants_11_14": round(persons * zs["enfants_11_14"], 1),
                      "jeunes_15_17": round(persons * zs["jeunes_15_17"], 1)}
        total += persons
        children += kids
    years = data["years"]
    level = "iris" if iris else "commune"
    return {
        "available": True,
        "year": builtup.nearest_year(years, year),
        "cells": cells,
        "total": round(total),
        "children_3_10": round(children),
        "density_per_built_ha": round(density, 1),
        "density_origin": density_origin if not iris else f"calibrée par quartier (IRIS INSEE {iris['year']})",
        "calibration": {"year": calib_year, "population": calib_pop, "basis": ctx["basis"], "built_ha": round(built_ha, 1), "level": level,
                        "zones": [{"code": k, "nom": z["nom"], "population": round(z["population"]), "built_ha": z["built_ha"],
                                   "density": round(z["density"] * scale, 1)} for k, z in (iris or {}).get("zones", {}).items()]},
        "age_shares": shares,
        "extrapolated": bool(calib_year and year > calib_year),
        "hypothesis": hypothesis,
        "method": ("Modèle dasymétrique : population de chaque quartier (IRIS INSEE) répartie au prorata de sa surface bâtie, "
                   "avec la structure par âge du quartier (occupation constante). Estimation, pas un recensement."
                   if iris else
                   "Modèle dasymétrique : population de référence répartie au prorata de la surface bâtie "
                   "(occupation constante). Estimation, pas un recensement."),
    }


def totals_by_year(commune: str, settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Population the built surface could house each year (constant occupancy) vs INSEE legal populations."""
    cfg = settings or get_settings()
    data = builtup.load(commune, cfg)
    if data is None:
        return {"available": False}
    calibration = _calibration(commune, data, cfg, use_hypothesis=False)  # once for every year of the series
    base = model(commune, max(data["years"]), cfg, data=data, calibration=calibration)
    insee = calibration["pops"]
    out = []
    for n, y in enumerate(data["years"]):
        built = sum(v[n] for v in data["cells"].values()) * CELL_HA
        out.append({"year": y, "built_ha": round(built, 1),
                    "model": model(commune, y, cfg, data=data, calibration=calibration)["total"],
                    "insee": int(insee[y]) if y in insee else None})
    return {"available": True, "density_per_built_ha": base.get("density_per_built_ha") or cfg.fallback_persons_per_built_ha,
            "series": out, "calibration": base.get("calibration"), "insee": {str(k): v for k, v in sorted(insee.items())}}
