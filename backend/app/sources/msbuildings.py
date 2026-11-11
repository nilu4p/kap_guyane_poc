"""Microsoft Global ML Building Footprints (ODbL), aggregated on the 200 m grid, keyless.

Footprints are published per zoom-9 quadkey as gzipped GeoJSON lines. Each file is
streamed, every polygon reduced at once to (cell, 1 building, area m²) and
discarded: **no footprint is ever stored or served** by the platform, only the
count and built area per 200 m cell (ethics charter).

Imagery dates are mixed (2014 → 2024 depending on the place): these counts give
the *shape* of the settlement (where people live, how dense), not a dated series.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import math
from typing import Dict, List, Optional, Sequence, Tuple

import httpx

from app.analyse.grid import cell_id, cell_of
from app.config import Settings, get_settings
from app.sources import health
from app.sources.http import USER_AGENT, cache_read, cache_read_stale, cache_write

logger = logging.getLogger(__name__)

ZOOM = 9
REGION = "FrenchGuiana"
INDEX_TTL = 30 * 24 * 3600
COUNTS_TTL = 90 * 24 * 3600
ALLOWED_PREFIX = "https://minedbuildings.z5.web.core.windows.net/global-buildings/"


class BuildingsError(RuntimeError):
    pass


def quadkey(x: int, y: int, z: int) -> str:
    digits = []
    for i in range(z, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if x & mask:
            digit += 1
        if y & mask:
            digit += 2
        digits.append(str(digit))
    return "".join(digits)


def _tile(lon: float, lat: float, z: int) -> Tuple[int, int]:
    n = 2 ** z
    lat_r = math.radians(max(min(lat, 85.0), -85.0))
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def quadkeys(bbox: Sequence[float], z: int = ZOOM) -> List[str]:
    west, south, east, north = bbox
    x0, y0 = _tile(west, north, z)
    x1, y1 = _tile(east, south, z)
    return [quadkey(x, y, z) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def index(settings: Optional[Settings] = None) -> Dict[str, List[str]]:
    """quadkey -> download URLs for French Guiana (the global index is 7 MB: only our rows are kept)."""
    cfg = settings or get_settings()
    cached = cache_read("msbuildings", "index", INDEX_TTL, cfg)
    if cached is not None:
        return cached
    try:
        response = httpx.get(cfg.ms_buildings_index_url, headers={"User-Agent": USER_AGENT}, timeout=120.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        health.record("microsoft_buildings", False, type(exc).__name__)
        stale = cache_read_stale("msbuildings", "index", cfg)
        if stale is not None:
            return stale
        raise BuildingsError(f"index des empreintes injoignable ({type(exc).__name__})") from exc
    out: Dict[str, List[str]] = {}
    for row in csv.DictReader(io.StringIO(response.text)):
        if row.get("Location") == REGION and (row.get("Url") or "").startswith(ALLOWED_PREFIX):
            out.setdefault(row["QuadKey"], []).append(row["Url"])
    cache_write("msbuildings", "index", out, cfg)
    health.record("microsoft_buildings", True)
    return out


def _ring_area_m2(ring: Sequence[Sequence[float]]) -> Tuple[float, float, float]:
    """(area m², centroid lon, centroid lat) of a lon/lat ring (local equirectangular)."""
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx = 111_320.0 * math.cos(math.radians(lat0))
    ky = 110_574.0
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(area) < 1e-18:
        return 0.0, ring[0][0], ring[0][1]
    return abs(area) / 2 * kx * ky, cx / (3 * area), cy / (3 * area)


def _aggregate(url: str, cfg: Settings) -> Dict[str, List[float]]:
    """{cell: [buildings, area m²]} of one quadkey file (disk-cached, polygons discarded)."""
    cached = cache_read("msbuildings_cells", url, COUNTS_TTL, cfg)
    if cached is not None:
        return cached
    try:
        response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=180.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        health.record("microsoft_buildings", False, type(exc).__name__)
        stale = cache_read_stale("msbuildings_cells", url, cfg)
        if stale is not None:
            return stale
        raise BuildingsError(f"empreintes injoignables ({type(exc).__name__})") from exc
    cells: Dict[str, List[float]] = {}
    with gzip.open(io.BytesIO(response.content), "rt", encoding="utf-8") as lines:
        for line in lines:
            try:
                geometry = json.loads(line)["geometry"]
                ring = geometry["coordinates"][0] if geometry["type"] == "Polygon" else geometry["coordinates"][0][0]
            except (ValueError, KeyError, IndexError, TypeError):
                continue
            area, lon, lat = _ring_area_m2(ring)
            cid = cell_id(*cell_of(lon, lat))
            entry = cells.setdefault(cid, [0, 0.0])
            entry[0] += 1
            entry[1] += area
    for entry in cells.values():
        entry[1] = round(entry[1], 1)
    cache_write("msbuildings_cells", url, cells, cfg)
    health.record("microsoft_buildings", True)
    return cells


def cells_in(bbox: Sequence[float], settings: Optional[Settings] = None) -> Dict[str, List[float]]:
    """{cell: [buildings, area m²]} for every footprint whose centroid falls in a cell of ``bbox``."""
    cfg = settings or get_settings()
    links = index(cfg)
    out: Dict[str, List[float]] = {}
    for qk in quadkeys(bbox):
        for url in links.get(qk, []):
            for cid, (count, area) in _aggregate(url, cfg).items():
                entry = out.setdefault(cid, [0, 0.0])
                entry[0] += count
                entry[1] += area
    return out
