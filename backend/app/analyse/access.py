"""Accessibility of facilities and siting of new ones (decision support).

**Accessibility** — for every inhabited 200 m cell, the straight-line distance to the
nearest facility of a family (×``detour_factor`` gives the order of magnitude of the
distance actually walked). A cell is *covered* when that straight-line distance is
within the family's radius (Administration › Paramètres).

**Siting** — *maximal covering location*: among the candidate cells, choose ``k``
sites one after the other, each time the cell that brings the largest **uncovered
demand** (inhabitants, or children of the right age for schools) within the radius,
then mark that demand as covered (greedy algorithm, within 63 % of the optimum and
explainable step by step). Candidate cells must satisfy the constraints:

| Constraint | Data | Default |
| --- | --- | --- |
| inside the commune | commune boundary (IGN) | always |
| not open water | Sentinel-2 water mask | on |
| room to build | built fraction of the cell (fused layer) | ≤ 60 % |
| served by a road | OpenStreetMap roads | ≤ 500 m |
| outside strict protected areas | WDPA (IUCN Ia-IV, reserves) | flagged, excluded on request; framed areas (regional park, adhesion area) flagged only |
| spacing between new sites | — | ≥ radius |

Land ownership and flood risk are **not known** to the platform: every proposed
site carries "foncier et risques à vérifier (cadastre, PPRI, EPFAG)".
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.analyse import builtup, layers as layer_store, population
from app.analyse.grid import CELL_HA, CELL_M, Window, cell_center, cell_id, haversine_m, mask_inside, nearest, parse_cell
from app.config import Settings, get_settings
from app.territoire import store

DEFAULT_CONSTRAINTS = {"exclude_water": True, "max_built_fraction": 0.6, "road_max_m": 500.0,
                       "exclude_protected": False, "min_spacing_m": None}


SCHOOL_CATEGORIES = ("ecole", "college", "lycee")


def radius_for(category: str, cfg: Settings) -> float:
    """Coverage radius of a family, as a *trip* distance (Administration › Paramètres)."""
    return float(cfg.coverage_radii_m.get(category, 1000))


def straight_radius(category: str, cfg: Settings, radius_m: Optional[float] = None) -> float:
    """Straight-line equivalent of the trip radius: radius / detour factor.

    Distances are computed as the crow flies; a household is covered when its estimated trip
    (straight line × detour factor) is within the radius. Setting the detour factor to 1 gives
    a straight-line coverage.
    """
    return float(radius_m or radius_for(category, cfg)) / max(cfg.detour_factor, 1.0)


def places_of(facility: Dict[str, Any], category: str, cfg: Settings) -> Optional[float]:
    """Pupil places of a school: a capacity entered in places, else classes × target class size.

    None = unknown (private schools without published classes, non-school facilities): treated
    as unlimited.
    """
    if category not in SCHOOL_CATEGORIES:
        return None
    unit = (facility.get("capacity_unit") or "").lower()
    if facility.get("capacity") and "place" in unit:
        return float(facility["capacity"])
    classes = (facility.get("attributes") or {}).get("classes")
    if classes:
        return float(classes) * cfg.school_class_size
    return None


def _facilities(commune: Dict[str, Any], category: str, cfg: Settings, include_planned: bool,
                extra_sites: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    """Facilities of a family around the commune (10 km margin: the next town's school counts too)."""
    west, south, east, north = commune["bbox"]
    margin = 0.09
    statuses = ("existant", "provisoire", "projet") if include_planned else ("existant", "provisoire")
    items = store.equipments(categories=[category], bbox=(west - margin, south - margin, east + margin, north + margin),
                             statuses=statuses, settings=cfg)
    return items + [dict(s, category=category, status="scenario") for s in extra_sites]


def accessibility(commune_code: str, category: str, year: int, settings: Optional[Settings] = None,
                  include_planned: bool = False, extra_sites: Sequence[Dict[str, Any]] = (),
                  use_hypothesis: bool = False, pop: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Distance to the nearest facility for every inhabited cell, coverage statistics."""
    cfg = settings or get_settings()
    commune = store.commune(commune_code, cfg)
    if commune is None:
        raise LookupError("Commune inconnue")
    pop = pop or population.model(commune_code, year, cfg, use_hypothesis=use_hypothesis)
    if not pop.get("available"):
        return {"available": False, "reason": pop.get("reason")}
    demand_key = store.CATEGORIES[category]["demand"]
    trip_radius = radius_for(category, cfg)
    radius = straight_radius(category, cfg)
    facilities = _facilities(commune, category, cfg, include_planned, extra_sites)
    cids = list(pop["cells"])
    centers = np.array([cell_center(*parse_cell(c)) for c in cids]) if cids else np.zeros((0, 2))
    dist, idx = nearest(centers[:, 0], centers[:, 1], np.array([f["lon"] for f in facilities]),
                        np.array([f["lat"] for f in facilities]))
    cells: Dict[str, Dict[str, Any]] = {}
    covered_demand = total_demand = covered_pop = total_pop = weighted = 0.0
    for n, cid in enumerate(cids):
        values = pop["cells"][cid]
        d = float(dist[n]) if math.isfinite(dist[n]) else None
        cells[cid] = {"distance_m": round(d) if d is not None else None, "facility": int(idx[n]) if d is not None else None,
                      "demand": values[demand_key], "pop": values["pop"]}
        total_demand += values[demand_key]
        total_pop += values["pop"]
        if d is not None:
            weighted += values["pop"] * d
            if d <= radius:
                covered_demand += values[demand_key]
                covered_pop += values["pop"]
    # Load of each facility: demand of the cells for which it is the nearest one (all cells), and the
    # part of it within the radius, compared with the school places (capacity-aware coverage).
    load: Dict[int, float] = {}
    load_in_radius: Dict[int, float] = {}
    for c in cells.values():
        if c["facility"] is not None:
            load[c["facility"]] = load.get(c["facility"], 0.0) + c["demand"]
            if c["distance_m"] is not None and c["distance_m"] <= radius:
                load_in_radius[c["facility"]] = load_in_radius.get(c["facility"], 0.0) + c["demand"]
    served_share: Dict[int, float] = {}
    places: Dict[int, Optional[float]] = {}
    for k, f in enumerate(facilities):
        places[k] = places_of(f, category, cfg)
        need = load_in_radius.get(k, 0.0)
        served_share[k] = min(1.0, places[k] / need) if places[k] is not None and need > 0 else 1.0
    served = 0.0
    for c in cells.values():
        covered = c["distance_m"] is not None and c["distance_m"] <= radius
        share = served_share.get(c["facility"], 1.0) if covered else 0.0
        c["served_share"] = round(share, 3)
        served += c["demand"] * share
    facility_rows = []
    for k, f in enumerate(facilities):
        facility_rows.append({
            "id": f.get("id"), "name": f.get("name") or store.CATEGORIES[category]["label"], "lat": f["lat"], "lon": f["lon"],
            "status": f.get("status"), "subtype": f.get("subtype"), "capacity": f.get("capacity"),
            "capacity_unit": f.get("capacity_unit"), "source": f.get("source"), "imprecise": bool(f.get("imprecise")),
            "catchment_demand": round(load.get(k, 0.0)), "demand_in_radius": round(load_in_radius.get(k, 0.0)),
            "places": round(places[k]) if places[k] is not None else None,
            "saturation": round(load_in_radius.get(k, 0.0) / places[k], 2) if places[k] else None,
            "attributes": {k2: v for k2, v in (f.get("attributes") or {}).items() if k2 in ("eleves", "classes", "rentree", "uai", "public")},
        })
    return {
        "available": True, "category": category, "label": store.CATEGORIES[category]["label"], "demand": demand_key,
        "radius_m": radius, "radius_trip_m": trip_radius, "detour_factor": cfg.detour_factor, "year": pop["year"],
        "cells": cells, "facilities": facility_rows,
        "stats": {
            "demand_total": round(total_demand), "demand_covered": round(covered_demand),
            "demand_uncovered": round(total_demand - covered_demand),
            "coverage_rate": round(covered_demand / total_demand, 3) if total_demand else None,
            # Capacity-aware: demand within the radius of a school that has a place for it.
            "demand_served": round(served), "demand_saturated": round(covered_demand - served),
            "served_rate": round(served / total_demand, 3) if total_demand else None,
            "saturated_facilities": sum(1 for r in facility_rows if r["saturation"] and r["saturation"] > 1),
            "population_total": round(total_pop), "population_covered": round(covered_pop),
            "mean_distance_m": round(weighted / total_pop) if total_pop else None,
            "facilities": len(facilities),
            "facilities_imprecise": sum(1 for f in facilities if f.get("imprecise")),
            "capacity_rule": (f"places = classes × {cfg.school_class_size} élèves" if category in SCHOOL_CATEGORIES else None),
        },
        "population": {k: pop[k] for k in ("total", "density_per_built_ha", "calibration", "extrapolated", "method", "hypothesis")},
    }


# --------------------------------------------------------------------------- constraints


def _road_cells(commune_code: str, cfg: Settings) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    stored = layer_store.load(commune_code, "roads", cfg)
    if stored is None or not stored[0]:
        return None
    centers = np.array([cell_center(*parse_cell(c)) for c in stored[0]])
    return centers[:, 0], centers[:, 1]


def _protected(commune_code: str, cfg: Settings) -> List[Tuple[str, str, Any]]:
    """(name, level 'stricte' / 'encadrée', prepared geometry) of the protected areas of the commune."""
    stored = layer_store.load(commune_code, "protected", cfg)
    if stored is None:
        return []
    import shapely
    from shapely.geometry import shape

    from app.sources.protected import _clean, level

    out = []
    for f in stored[0]:
        try:
            geom = shape(f["geometry"])
            shapely.prepare(geom)
            props = f.get("properties") or {}
            lvl = props.get("level") or level(str(props.get("iucn") or ""), _clean(props.get("designation") or ""))
            out.append((_clean(props.get("name") or "Aire protégée"), lvl, geom))
        except Exception:
            continue
    # Strict protections first: a cell in both keeps the strict label.
    return sorted(out, key=lambda t: t[1] != "stricte")


def _disk(radius_m: float) -> List[Tuple[int, int]]:
    r = int(math.ceil(radius_m / CELL_M))
    return [(dr, dc) for dr in range(-r, r + 1) for dc in range(-r, r + 1) if math.hypot(dr, dc) * CELL_M <= radius_m]


def _shifted_sum(values: np.ndarray, offsets: Sequence[Tuple[int, int]]) -> np.ndarray:
    """Sum of ``values`` over the disk around each cell (array indices: i southward, j eastward)."""
    out = np.zeros_like(values)
    rows, cols = values.shape
    for dr, dc in offsets:
        di, dj = -dr, dc  # a row northwards is one index up
        src = values[max(0, di):rows + min(0, di), max(0, dj):cols + min(0, dj)]
        out[max(0, -di):rows + min(0, -di), max(0, -dj):cols + min(0, -dj)] += src
    return out


def site(commune_code: str, category: str, k: int = 3, year: Optional[int] = None,
         constraints: Optional[Dict[str, Any]] = None, radius_m: Optional[float] = None,
         settings: Optional[Settings] = None, use_hypothesis: bool = False, include_planned: bool = True) -> Dict[str, Any]:
    """Recommend ``k`` sites for a new facility of ``category`` (greedy maximal covering)."""
    cfg = settings or get_settings()
    commune = store.commune(commune_code, cfg)
    if commune is None:
        raise LookupError("Commune inconnue")
    data = builtup.load(commune_code, cfg)
    if data is None:
        return {"available": False, "reason": "Analyse du bâti non réalisée pour cette commune (onglet Analyses)."}
    year = year or max(data["years"])
    rules = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    trip_radius = float(radius_m or radius_for(category, cfg))
    radius = straight_radius(category, cfg, trip_radius)
    spacing = float(rules.get("min_spacing_m") or trip_radius) / max(cfg.detour_factor, 1.0)
    acc = accessibility(commune_code, category, year, cfg, include_planned=include_planned, use_hypothesis=use_hypothesis)
    if not acc.get("available"):
        return acc
    cells = acc["cells"]
    if not cells:
        return {"available": False, "reason": "Aucun carreau habité estimé dans la commune pour cette année : rien à desservir."}
    rows_ = [parse_cell(c)[0] for c in cells]
    cols_ = [parse_cell(c)[1] for c in cells]
    pad = int(math.ceil(radius / CELL_M)) + 2
    window = Window(min(rows_) - pad, min(cols_) - pad, max(rows_) + pad, max(cols_) + pad)
    residual = np.zeros(window.shape)
    demand = np.zeros(window.shape)
    for cid, c in cells.items():
        i, j = window.index(*parse_cell(cid))
        demand[i, j] = c["demand"]
        # Not covered, or covered by a saturated school: the part without a place is residual demand.
        residual[i, j] = c["demand"] * (1.0 - c.get("served_share", 0.0))
    inside = mask_inside(window, commune["contour"])
    built_now = window.from_sparse(builtup.year_values(data, year))
    water_layer = layer_store.load(commune_code, "water", cfg)
    water = window.from_sparse(water_layer[0]) if water_layer else np.zeros(window.shape)
    lon, lat = window.centers()
    candidates = inside.copy()
    # Candidates stay close to where people live (within the radius of some inhabitant).
    near_people = _shifted_sum((demand > 0).astype(float), _disk(radius)) > 0
    candidates &= near_people
    if rules["exclude_water"]:
        candidates &= water < 0.3
    candidates &= built_now <= float(rules["max_built_fraction"])
    road_dist = np.full(window.shape, np.nan)
    roads = _road_cells(commune_code, cfg)
    if roads is not None:
        idx = np.nonzero(candidates)
        d, _ = nearest(lon[idx], lat[idx], roads[0], roads[1])
        road_dist[idx] = d
        if rules.get("road_max_m"):
            candidates &= ~(road_dist > float(rules["road_max_m"]))
    protected = _protected(commune_code, cfg)
    protected_name = np.full(window.shape, "", dtype=object)
    protected_level = np.full(window.shape, "", dtype=object)
    if protected:
        import shapely

        idx = np.nonzero(candidates)
        for name, lvl, geom in protected:
            hit = shapely.contains_xy(geom, lon[idx], lat[idx])
            for i, j in zip(idx[0][hit], idx[1][hit]):
                if not protected_name[i, j]:
                    protected_name[i, j], protected_level[i, j] = name, lvl
        if rules["exclude_protected"]:  # strict protections only: regional park / adhesion areas are inhabited
            candidates &= protected_level != "stricte"
    disk = _disk(radius)
    growth = window.from_sparse(builtup.growth(data, builtup.nearest_year(data["years"], 2019), year))
    chosen: List[Dict[str, Any]] = []
    available = candidates.copy()
    for rank in range(1, max(1, k) + 1):
        gain = _shifted_sum(residual, disk)
        gain = np.where(available, gain, -1.0)
        best = np.unravel_index(int(np.argmax(gain)), gain.shape)
        if gain[best] <= 0:
            break
        i, j = int(best[0]), int(best[1])
        r, c = window.cell_at(i, j)
        site_lon, site_lat = cell_center(r, c)
        catch = np.zeros(window.shape, dtype=bool)
        for dr, dc in disk:
            ii, jj = i - dr, j + dc
            if 0 <= ii < window.shape[0] and 0 <= jj < window.shape[1]:
                catch[ii, jj] = True
        current = cells.get(cell_id(r, c), {}).get("distance_m")
        if current is None:
            fac = acc["facilities"]
            if fac:
                current = round(float(min(haversine_m(site_lon, site_lat, f["lon"], f["lat"]) for f in fac)))
        pop_in = sum(cells[cid]["pop"] for cid in cells if catch[window.index(*parse_cell(cid))])
        checks = [
            {"label": "Dans la commune", "status": "ok"},
            {"label": "Hors plan d'eau", "status": "ok" if water[i, j] < 0.3 else "attention",
             "detail": f"eau {water[i, j]:.0%} du carreau" if water_layer else "masque d'eau non calculé"},
            {"label": "Place disponible (bâti du carreau)", "status": "ok" if built_now[i, j] <= 0.4 else "attention",
             "detail": f"{built_now[i, j]:.0%} du carreau bâti"},
            {"label": "Desserte routière (OSM)",
             "status": "non vérifié" if math.isnan(road_dist[i, j]) else ("ok" if road_dist[i, j] <= 300 else "attention"),
             "detail": "routes non chargées" if math.isnan(road_dist[i, j]) else f"route à ~{round(road_dist[i, j], -1):.0f} m"},
            {"label": "Aire protégée (WDPA)", "status": "attention" if protected_name[i, j] else ("ok" if protected else "non vérifié"),
             "detail": (f"{protected_name[i, j]} — protection {protected_level[i, j]}"
                        + (" : construction très encadrée ou interdite" if protected_level[i, j] == "stricte"
                           else " : règlement du parc / de la zone à consulter")) if protected_name[i, j]
                       else ("aucune" if protected else "couche non chargée")},
            _land_check(r, c, cfg),
            {"label": "Propriété, risques (PPRI), réseaux", "status": "non vérifié",
             "detail": "propriétaire (État pour l'essentiel du foncier guyanais), PPRI et réseaux à vérifier avec la DGTM / l'EPFAG"},
        ]
        chosen.append({
            "rank": rank, "cell": cell_id(r, c), "lat": round(site_lat, 6), "lon": round(site_lon, 6),
            "gain_demand": round(float(gain[best])), "demand_label": acc["demand"],
            "catchment_population": round(pop_in),
            "catchment_growth_ha": round(float(growth[catch].sum()), 2),
            "current_nearest_m": current, "road_m": None if math.isnan(road_dist[i, j]) else round(float(road_dist[i, j])),
            "built_fraction": round(float(built_now[i, j]), 2), "checks": checks,
            "why": _why(acc, float(gain[best]), pop_in, float(growth[catch].sum()), current, trip_radius),
        })
        residual[catch] = 0.0
        for dr, dc in _disk(spacing):
            ii, jj = i - dr, j + dc
            if 0 <= ii < window.shape[0] and 0 <= jj < window.shape[1]:
                available[ii, jj] = False
    gained = sum(s["gain_demand"] for s in chosen)
    before = acc["stats"]
    base_served = before.get("demand_served", before["demand_covered"])
    classes = None
    if category == "ecole":
        ratio = _pupils_per_class(commune_code, cfg)
        classes = {"pupils_per_class": ratio,
                   "per_site": [math.ceil(s["gain_demand"] / ratio) if ratio else None for s in chosen]}
    return {
        "available": True, "commune": commune_code, "category": category, "label": acc["label"], "year": acc["year"],
        "radius_m": trip_radius, "radius_straight_m": round(radius), "k": k, "constraints": rules, "sites": chosen, "classes": classes,
        "candidates": int(candidates.sum()),
        "before": {**before, "coverage_rate": before.get("served_rate", before["coverage_rate"]), "demand_covered": base_served},
        "after": {"demand_covered": base_served + gained,
                  "coverage_rate": round((base_served + gained) / before["demand_total"], 3) if before["demand_total"] else None},
        "population": acc["population"],
        "method": "Couverture maximale gloutonne : chaque site retenu est le carreau qui couvre le plus de demande non "
                  "encore desservie dans le rayon, sous contraintes. Distances à vol d'oiseau.",
    }


def _land_check(row: int, col: int, cfg: Settings) -> Dict[str, Any]:
    """Aggregated cadastre check of the candidate cell (no parcel identifier, no owner)."""
    from app.analyse.grid import cell_bounds
    from app.sources import cadastre

    try:
        summary = cadastre.cell_summary(cell_bounds(row, col), cfg)
    except Exception:
        summary = None
    if summary is None:
        return {"label": "Foncier (cadastre)", "status": "non vérifié", "detail": "cadastre injoignable"}
    if summary["parcels"] == 0:
        return {"label": "Foncier (cadastre)", "status": "attention",
                "detail": "aucune parcelle cadastrée dans le carreau (domaine non cadastré : situation foncière à établir)"}
    status = "ok" if summary["large_parcels"] else "attention"
    return {"label": "Foncier (cadastre)", "status": status,
            "detail": f"{summary['parcels']} parcelle(s), la plus grande {summary['largest_m2']:,} m² ; "
                      f"{summary['large_parcels']} de plus de {cadastre.LARGE_M2:,} m²".replace(",", " ")}


def _why(acc: Dict[str, Any], gain: float, pop_in: float, growth_ha: float, current: Optional[float], radius: float) -> str:
    demand_label = {"enfants_3_10": "enfants de 3 à 10 ans", "enfants_11_14": "jeunes de 11 à 14 ans",
                    "jeunes_15_17": "jeunes de 15 à 17 ans", "pop": "habitants"}[acc["demand"]]
    parts = [f"≈ {round(gain):,} {demand_label} sans place à moins de {radius / 1000:.1f} km de trajet (hors desserte ou école "
             f"saturée) seraient desservis".replace(",", " ")]
    if current is not None:
        parts.append(f"équipement le plus proche actuellement à {current / 1000:.1f} km à vol d'oiseau")
    if growth_ha > 0.5:
        parts.append(f"+{growth_ha:.1f} ha bâtis depuis 2019 dans la zone desservie (croissance mesurée par satellite)")
    parts.append(f"≈ {round(pop_in):,} habitants estimés dans le rayon".replace(",", " "))
    return " ; ".join(parts) + "."


def _pupils_per_class(commune_code: str, cfg: Settings) -> Optional[float]:
    s = store.series(commune_code, ("ecoles_pub_eleves", "ecoles_pub_classes"), cfg)
    pupils, classes = s.get("ecoles_pub_eleves") or {}, s.get("ecoles_pub_classes") or {}
    years = sorted(set(pupils) & set(classes))
    if not years or not classes[years[-1]]:
        return None
    return round(pupils[years[-1]] / classes[years[-1]], 1)


def evaluate(commune_code: str, category: str, sites: Sequence[Dict[str, Any]], year: Optional[int] = None,
             settings: Optional[Settings] = None, use_hypothesis: bool = False) -> Dict[str, Any]:
    """Coverage before / after adding ``sites`` (a scenario drawn or accepted by the user)."""
    cfg = settings or get_settings()
    data = builtup.load(commune_code, cfg)
    if data is None:
        return {"available": False, "reason": "Analyse du bâti non réalisée pour cette commune."}
    year = year or max(data["years"])
    pop = population.model(commune_code, year, cfg, use_hypothesis=use_hypothesis)
    before = accessibility(commune_code, category, year, cfg, include_planned=True, use_hypothesis=use_hypothesis, pop=pop)
    after = accessibility(commune_code, category, year, cfg, include_planned=True, extra_sites=sites,
                          use_hypothesis=use_hypothesis, pop=pop)
    if not before.get("available"):
        return before
    per_site = after["facilities"][-len(sites):] if sites else []
    return {
        "available": True, "year": before["year"], "radius_m": before["radius_trip_m"],
        "before": {**before["stats"], "coverage_rate": before["stats"]["served_rate"], "demand_covered": before["stats"]["demand_served"]},
        "after": {**after["stats"], "coverage_rate": after["stats"]["served_rate"], "demand_covered": after["stats"]["demand_served"]},
        "gain": {"demand": after["stats"]["demand_served"] - before["stats"]["demand_served"],
                 "population": after["stats"]["population_covered"] - before["stats"]["population_covered"]},
        "sites": [{**s, "catchment_demand": p["catchment_demand"]} for s, p in zip(sites, per_site)],
        "population": before["population"],
    }
