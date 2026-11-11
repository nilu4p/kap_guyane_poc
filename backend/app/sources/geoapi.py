"""The 22 communes of French Guiana: boundaries, legal population, area, intercommunality.

Source: API Découpage administratif (geo.api.gouv.fr — IGN Admin Express / INSEE),
keyless. A snapshot of the same request is bundled in ``app/reference`` so the
platform starts (and demonstrates) without network; a live refresh replaces it.
"""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import Settings, get_settings
from app.sources.http import cache_read, cache_read_stale, cache_write, get_json

logger = logging.getLogger(__name__)

REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "communes_973.geojson.gz"
FIELDS = "nom,code,codesPostaux,population,surface,centre,codeEpci,epci,contour"
TTL = 30 * 24 * 3600


def _round(coords: Any) -> Any:
    if coords and isinstance(coords[0], (int, float)):
        return [round(coords[0], 5), round(coords[1], 5)]
    return [_round(c) for c in coords]


def bundled() -> Dict[str, Any]:
    with gzip.open(REFERENCE, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_communes(settings: Optional[Settings] = None, live: bool = True) -> Dict[str, Any]:
    """FeatureCollection of the department's communes, with where it came from."""
    cfg = settings or get_settings()
    url = f"{cfg.geo_api_url}/departements/{cfg.department_code}/communes"
    key = f"{url}?{FIELDS}"
    data = cache_read("geoapi", key, TTL, cfg) if live else None
    origin = "cache"
    if data is None and live:
        data = get_json(url, params={"fields": FIELDS, "format": "geojson", "geometry": "contour"},
                        settings=cfg, source="geo.api.gouv.fr")
        if data and data.get("features"):
            for feature in data["features"]:
                feature["geometry"]["coordinates"] = _round(feature["geometry"]["coordinates"])
            cache_write("geoapi", key, data, cfg)
            origin = "live"
        else:
            data = cache_read_stale("geoapi", key, cfg)
    if not data or not data.get("features"):
        data = bundled()
        origin = "snapshot"
    data = dict(data)
    data["origin"] = origin
    return data


def normalise(feature: Dict[str, Any]) -> Dict[str, Any]:
    """One commune row: code, name, EPCI, population, area (ha), centre, bbox, contour."""
    from app.core.geo import bbox_of

    props = feature.get("properties") or {}
    epci = props.get("epci")
    centre = (props.get("centre") or {}).get("coordinates") or [None, None]
    return {
        "code": props["code"],
        "nom": props.get("nom", props["code"]),
        "epci": epci.get("nom", "") if isinstance(epci, dict) else str(props.get("codeEpci") or ""),
        "population": props.get("population"),
        "surface_ha": props.get("surface"),
        "centre_lon": centre[0],
        "centre_lat": centre[1],
        "bbox": list(bbox_of(feature["geometry"]) or []),
        "contour": feature["geometry"],
    }


def communes(settings: Optional[Settings] = None, live: bool = True) -> List[Dict[str, Any]]:
    data = fetch_communes(settings, live)
    rows = [normalise(f) for f in data["features"] if (f.get("properties") or {}).get("code")]
    for r in rows:
        r["origin"] = data["origin"]
    return sorted(rows, key=lambda r: r["code"])
