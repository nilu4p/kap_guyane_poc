"""Territorial watch: neighbourhoods that grew, and whether facilities followed.

- **Growth clusters** — 200 m cells whose built surface grew by at least
  ``MIN_GROWTH_HA`` since the reference year, grouped into connected clusters
  ("quartiers en croissance"): built hectares gained, estimated new buildings
  (hectares × buildings per built hectare measured on the commune), estimated new
  inhabitants (constant occupancy), and distance to the nearest school, water point
  and health facility.
- **Census scout list** ("Recensement Éclaireur") — the cells to point out to INSEE
  before the January collection so that the building register (RIL) is checked
  there. Aggregated cells only; cells with fewer than ``privacy_min_buildings``
  estimated new buildings are not listed individually (secrecy rule), they are
  summed in a single "other cells" line.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from app.analyse import builtup, population
from app.analyse.grid import CELL_HA, cell_center, cell_id, haversine_m, nearest, parse_cell
from app.config import Settings, get_settings
from app.territoire import store

MIN_GROWTH_HA = 0.4
WATCH_CATEGORIES = ("ecole", "eau", "sante")


def _clusters(cells: List[str]) -> List[List[str]]:
    todo = set(cells)
    groups = []
    for start in sorted(cells):  # deterministic grouping (a set pops in a per-process order)
        if start not in todo:
            continue
        todo.remove(start)
        group, stack = [start], [start]
        while stack:
            r, c = parse_cell(stack.pop())
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    n = cell_id(r + dr, c + dc)
                    if n in todo:
                        todo.remove(n)
                        group.append(n)
                        stack.append(n)
        groups.append(group)
    return groups


def hotspots(commune_code: str, settings: Optional[Settings] = None, since: int = 2019,
             until: Optional[int] = None, notify: bool = True) -> Dict[str, Any]:
    cfg = settings or get_settings()
    data = builtup.load(commune_code, cfg)
    commune = store.commune(commune_code, cfg)
    if data is None or commune is None:
        return {"available": False, "clusters": [], "summary": None}
    until = until or max(data["years"])
    since = builtup.nearest_year(data["years"], since)
    growth = builtup.growth(data, since, until)
    per_ha = data["meta"].get("buildings_per_built_ha")
    pop = population.model(commune_code, until, cfg)
    density = pop.get("density_per_built_ha") or cfg.fallback_persons_per_built_ha
    from app.analyse.access import straight_radius

    strong = [c for c, v in growth.items() if v >= MIN_GROWTH_HA]
    west, south, east, north = commune["bbox"]
    margin = 0.09
    facilities = {cat: store.equipments(categories=[cat], bbox=(west - margin, south - margin, east + margin, north + margin),
                                        settings=cfg) for cat in WATCH_CATEGORIES}
    clusters = []
    for group in _clusters(strong):
        gained = sum(growth[c] for c in group)
        if gained < 1.0:
            continue
        lons, lats = zip(*(cell_center(*parse_cell(c)) for c in group))
        weights = np.array([growth[c] for c in group])
        lon = float(np.average(lons, weights=weights))
        lat = float(np.average(lats, weights=weights))
        nearest_by_cat = {}
        for cat, items in facilities.items():
            if not items:
                nearest_by_cat[cat] = None
                continue
            d = haversine_m(lon, lat, np.array([f["lon"] for f in items]), np.array([f["lat"] for f in items]))
            k = int(np.argmin(d))
            nearest_by_cat[cat] = {"distance_m": round(float(d[k])), "name": items[k]["name"] or store.CATEGORIES[cat]["label"]}
        school = nearest_by_cat.get("ecole")
        far_school = school is None or school["distance_m"] > straight_radius("ecole", cfg)
        clusters.append({
            "cells": len(group), "growth_ha": round(gained, 1),
            "new_buildings": round(gained * per_ha) if per_ha else None,
            "new_inhabitants": round(gained * density),
            "lat": round(lat, 5), "lon": round(lon, 5), "nearest": nearest_by_cat,
            "far_from_school": far_school,
            "landmark": (school or {}).get("name"),
            "cell_ids": group,
        })
    clusters.sort(key=lambda c: (-c["growth_ha"], -c["lat"], c["lon"]))
    summary = {
        "since": since, "until": until, "clusters": len(clusters),
        "growth_ha": round(sum(v for v in growth.values() if v > 0), 1),
        "far_from_school_ha": round(sum(c["growth_ha"] for c in clusters if c["far_from_school"]), 1),
        "top": [{k: c[k] for k in ("growth_ha", "new_inhabitants", "landmark", "far_from_school")} for c in clusters[:3]],
    }
    if notify and clusters:
        from app.services import notify as notifier

        top = clusters[0]
        notifier.notify_event(
            "veille", f"Veille — {commune['nom']} : {summary['growth_ha']} ha bâtis gagnés depuis {since}", level="warning",
            details={"Quartiers en croissance": len(clusters),
                     "Dont loin d'une école (ha)": summary["far_from_school_ha"],
                     "Premier foyer": f"+{top['growth_ha']} ha près de {top['landmark'] or '—'}"},
            view=f"atlas/{commune_code}", label="Voir sur l'atlas", key=f"watch:{commune_code}:{until}", cooldown=24 * 3600,
            settings=cfg,
        )
    return {"available": True, "clusters": clusters, "summary": summary,
            "method": "Croissance de la surface bâtie fusionnée (WSF 2019 + Sentinel-2) ; bâtiments et habitants estimés "
                      "à partir de densités mesurées sur la commune. Estimations agrégées à 200 m."}


def census_scout(commune_code: str, since: int, settings: Optional[Settings] = None,
                 until: Optional[int] = None) -> Dict[str, Any]:
    """Cells to point out to INSEE (aggregated, secrecy rule applied)."""
    cfg = settings or get_settings()
    data = builtup.load(commune_code, cfg)
    if data is None:
        return {"available": False, "rows": []}
    until = until or max(data["years"])
    since = builtup.nearest_year(data["years"], since)
    growth = builtup.growth(data, since, until)
    per_ha = data["meta"].get("buildings_per_built_ha") or 0
    built_now = builtup.year_values(data, until)  # once: per listed cell it made the export quadratic
    rows, hidden_cells, hidden_ha = [], 0, 0.0
    for cid, gained in sorted(growth.items(), key=lambda kv: (-kv[1], kv[0])):  # stable order: signed lists are reproducible
        if gained <= 0:
            continue
        buildings = gained * per_ha if per_ha else None
        if buildings is None or buildings < cfg.privacy_min_buildings:
            hidden_cells += 1
            hidden_ha += gained
            continue
        lon, lat = cell_center(*parse_cell(cid))
        rows.append({"cell": cid, "lat": round(lat, 5), "lon": round(lon, 5), "growth_ha": round(gained, 2),
                     "new_buildings_est": round(buildings), "built_share_now": round(built_now.get(cid, 0.0), 2)})
    return {
        "available": True, "since": since, "until": until, "rows": rows,
        "hidden": {"cells": hidden_cells, "growth_ha": round(hidden_ha, 2),
                   "rule": f"carreaux de moins de {cfg.privacy_min_buildings} bâtiments estimés non listés"},
        "buildings_per_built_ha": per_ha,
        "cell_size_m": int(cfg.grid_cell_m),
        "notice": "Liste agrégée par carreaux de 200 m, issue de l'imagerie satellitaire. Aucune construction individuelle n'est "
                  "désignée ; aucune distinction légal / illégal. Usage : appui à la mise à jour du RIL avec l'INSEE. "
                  "Tout usage fiscal, de contrôle ou d'expulsion est exclu (charte d'usage).",
    }
