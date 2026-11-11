"""Land parcels around a candidate site (IGN API Carto, cadastre module), keyless.

Used only as an *aggregated* land check of a 200 m candidate cell: how many parcels, the
largest one, how many are large enough for a facility. No parcel identifier and no owner
are ever returned (the cadastre's owner files — MAJIC — are excluded by the charter).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Sequence

from app.config import Settings, get_settings
from app.sources.http import cache_read, cache_write, get_json

logger = logging.getLogger(__name__)

API = "https://apicarto.ign.fr/api/cadastre/parcelle"
TTL = 30 * 24 * 3600
LARGE_M2 = 5000  # a primary school with its yard needs about 0.5 to 1 ha


def cell_summary(bounds: Sequence[float], settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    """{"parcels", "largest_m2", "large_parcels"} for the parcels intersecting a cell; None if unavailable."""
    cfg = settings or get_settings()
    west, south, east, north = bounds
    polygon = {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}
    key = json.dumps([round(v, 6) for v in bounds])
    data = cache_read("cadastre", key, TTL, cfg)
    if data is None:
        data = get_json(API, params={"geom": json.dumps(polygon), "_limit": 500}, settings=cfg, source="cadastre_ign")
        if not data or not isinstance(data.get("features"), list):
            return None
        cache_write("cadastre", key, data, cfg)
    areas = [float((f.get("properties") or {}).get("contenance") or 0) for f in data["features"]]
    return {"parcels": len(areas), "largest_m2": round(max(areas)) if areas else 0,
            "large_parcels": sum(1 for a in areas if a >= LARGE_M2)}
