"""Statistical secrecy of the 200 m layers served to the console (ethics charter).

The 200 m cell protects households in towns, not in sparse areas: a cell holding one
building in the forest *is* one household. Every layer leaving the API therefore
applies the same rule as the exports:

- a cell is **sparse** when it holds fewer than ``privacy_min_buildings`` buildings
  (Microsoft footprints count, or built hectares × buildings per built hectare when the
  footprints do not cover the cell);
- building counts below the threshold are replaced by :data:`BELOW` ("< seuil");
- the inhabitants and children of a sparse cell are not shown (:data:`BELOW`);
- the built share of a sparse cell is rounded to 5 % (no single roof readable);
- growth is shown only above the surface of ``privacy_min_buildings`` buildings.

Computations (accessibility, siting) keep the exact values: only what is displayed or
exported is generalised.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Set

from app.analyse.grid import CELL_HA
from app.config import Settings, get_settings

BELOW = -1  # "fewer than the secrecy threshold" (rendered "< 5" by the console)


def buildings_per_ha(meta: Optional[Dict[str, Any]]) -> float:
    value = (meta or {}).get("buildings_per_built_ha")
    return float(value) if value else 20.0  # order of magnitude in Guiana towns


def sparse_cells(built: Dict[str, float], buildings: Optional[Dict[str, Any]], meta: Optional[Dict[str, Any]],
                 settings: Optional[Settings] = None) -> Set[str]:
    """Cells holding fewer than the threshold of buildings (footprints, or estimate from the built surface)."""
    cfg = settings or get_settings()
    threshold = cfg.privacy_min_buildings
    per_ha = buildings_per_ha(meta)
    out = set()
    for cid in set(built) | set(buildings or {}):
        if buildings and cid in buildings:
            count = buildings[cid][0] if isinstance(buildings[cid], list) else buildings[cid]
            estimate = max(count, built.get(cid, 0.0) * CELL_HA * per_ha)
        else:
            estimate = built.get(cid, 0.0) * CELL_HA * per_ha
        if estimate < threshold:
            out.add(cid)
    return out


def min_growth_ha(meta: Optional[Dict[str, Any]], settings: Optional[Settings] = None) -> float:
    cfg = settings or get_settings()
    return round(cfg.privacy_min_buildings / buildings_per_ha(meta), 3)


def generalise_share(value: float) -> float:
    """Built share rounded to 5 % (at least 5 % when something is built)."""
    if value <= 0:
        return 0.0
    return max(0.05, round(value * 20) / 20)


def generalise_count(value: float, settings: Optional[Settings] = None) -> float:
    cfg = settings or get_settings()
    return BELOW if value < cfg.privacy_min_buildings else value


def round_people(value: float) -> float:
    """Inhabitants rounded to 5 (estimates never pretend to the unit)."""
    return float(5 * math.floor(value / 5 + 0.5))
