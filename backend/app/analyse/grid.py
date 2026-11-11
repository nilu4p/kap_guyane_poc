"""The 200 m aggregation grid shared by every layer of the platform.

One global grid anchored on French Guiana (lon/lat aligned, no projection library):
a cell is ``DLAT`` degrees high and ``DLON`` degrees wide, which is 200 m × 200 m at
4° N. Between 2° N and 6° N the east-west size varies by less than 0.3 %: negligible
for planning, and it keeps every cell identifier stable across communes and years.

- cell id ``"<row>_<col>"``: row counted northwards from ``LAT0``, column eastwards
  from ``LON0``;
- a *window* is the rectangle of cells covering a bounding box; its arrays are indexed
  ``[i, j]`` with ``i = 0`` on the northern edge (raster convention), so rasterio can
  write into it directly with :func:`transform`.

The 200 m cell is the ethics floor: no layer is ever stored or exported finer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np

CELL_M = 200.0
LAT0, LON0 = 1.5, -55.5
REF_LAT = 4.0
DLAT = CELL_M / 110_574.0
DLON = CELL_M / (111_320.0 * math.cos(math.radians(REF_LAT)))
CELL_HA = CELL_M * CELL_M / 10_000.0


def cell_id(row: int, col: int) -> str:
    return f"{row}_{col}"


def parse_cell(cid: str) -> Tuple[int, int]:
    row, col = cid.split("_")
    return int(row), int(col)


def cell_of(lon: float, lat: float) -> Tuple[int, int]:
    return int(math.floor((lat - LAT0) / DLAT)), int(math.floor((lon - LON0) / DLON))


def cell_bounds(row: int, col: int) -> Tuple[float, float, float, float]:
    """(west, south, east, north) of a cell."""
    west = LON0 + col * DLON
    south = LAT0 + row * DLAT
    return west, south, west + DLON, south + DLAT


def cell_center(row: int, col: int) -> Tuple[float, float]:
    """(lon, lat) of the centre of a cell."""
    return LON0 + (col + 0.5) * DLON, LAT0 + (row + 0.5) * DLAT


def cell_polygon(cid: str, ndigits: int = 6) -> Dict[str, Any]:
    west, south, east, north = cell_bounds(*parse_cell(cid))
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [[[round(x, ndigits), round(y, ndigits)] for x, y in ring]]}


@dataclass(frozen=True)
class Window:
    """Rectangle of grid cells: rows ``row0..row1`` and columns ``col0..col1`` (inclusive)."""

    row0: int
    col0: int
    row1: int
    col1: int

    @classmethod
    def from_bbox(cls, bbox: Sequence[float]) -> "Window":
        west, south, east, north = bbox
        r0, c0 = cell_of(west, south)
        r1, c1 = cell_of(east, north)
        return cls(r0, c0, r1, c1)

    @property
    def shape(self) -> Tuple[int, int]:
        return self.row1 - self.row0 + 1, self.col1 - self.col0 + 1

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        west, south, _, _ = cell_bounds(self.row0, self.col0)
        _, _, east, north = cell_bounds(self.row1, self.col1)
        return west, south, east, north

    @property
    def area_km2(self) -> float:
        rows, cols = self.shape
        return rows * cols * CELL_M * CELL_M / 1e6

    def transform(self) -> Any:
        """Affine transform of the window arrays (north-up, EPSG:4326)."""
        from rasterio.transform import from_origin

        west, _, _, north = self.bbox
        return from_origin(west, north, DLON, DLAT)

    def index(self, row: int, col: int) -> Tuple[int, int]:
        return self.row1 - row, col - self.col0

    def cell_at(self, i: int, j: int) -> Tuple[int, int]:
        return self.row1 - i, self.col0 + j

    def centers(self) -> Tuple[np.ndarray, np.ndarray]:
        """Arrays (lon, lat) of the cell centres, shape = window shape."""
        rows, cols = self.shape
        lons = LON0 + (np.arange(self.col0, self.col0 + cols) + 0.5) * DLON
        lats = LAT0 + (np.arange(self.row1, self.row1 - rows, -1) + 0.5) * DLAT
        return np.meshgrid(lons, lats)

    def blocks(self, size: int) -> Iterator["Window"]:
        """Split into square sub-windows of ``size`` cells (edges clipped)."""
        for r in range(self.row0, self.row1 + 1, size):
            for c in range(self.col0, self.col1 + 1, size):
                yield Window(r, c, min(r + size - 1, self.row1), min(c + size - 1, self.col1))

    def to_sparse(self, array: np.ndarray, mask: Optional[np.ndarray] = None, ndigits: int = 4) -> Dict[str, float]:
        """Non-zero (and masked-in) values of a window array, keyed by cell id."""
        keep = np.isfinite(array) & (array != 0)
        if mask is not None:
            keep &= mask
        out: Dict[str, float] = {}
        for i, j in zip(*np.nonzero(keep)):
            row, col = self.cell_at(int(i), int(j))
            out[cell_id(row, col)] = round(float(array[i, j]), ndigits)
        return out

    def from_sparse(self, values: Dict[str, float], fill: float = 0.0) -> np.ndarray:
        array = np.full(self.shape, fill, dtype="float64")
        for cid, value in values.items():
            row, col = parse_cell(cid)
            if self.row0 <= row <= self.row1 and self.col0 <= col <= self.col1:
                i, j = self.index(row, col)
                array[i, j] = value
        return array


def mask_inside(window: Window, geometry: Dict[str, Any]) -> np.ndarray:
    """Boolean window array: cell centre inside the (Multi)Polygon ``geometry``."""
    import shapely
    from shapely.geometry import shape

    geom = shape(geometry)
    shapely.prepare(geom)
    lon, lat = window.centers()
    return shapely.contains_xy(geom, lon, lat)


def cells_geojson(layers: Dict[str, Dict[str, float]], cells: Iterable[str], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """FeatureCollection of 200 m squares carrying the value of each named layer."""
    features: List[Dict[str, Any]] = []
    for cid in cells:
        props: Dict[str, Any] = {"cell": cid}
        for name, values in layers.items():
            if cid in values:
                props[name] = values[cid]
        features.append({"type": "Feature", "geometry": cell_polygon(cid), "properties": props})
    return {"type": "FeatureCollection", "features": features, **(extra or {})}


def haversine_m(lon1: np.ndarray, lat1: np.ndarray, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    """Great-circle distance in metres (numpy broadcasting)."""
    lon1, lat1, lon2, lat2 = (np.radians(np.asarray(a, dtype="float64")) for a in (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


# Largest points × targets distance matrix computed at once (~32 MB of float64 per temporary):
# with tens of thousands of road cells as targets a fixed chunk of points would need gigabytes.
MAX_PAIRS_PER_CHUNK = 4_000_000


def nearest(points_lon: np.ndarray, points_lat: np.ndarray, targets_lon: np.ndarray, targets_lat: np.ndarray,
            chunk: int = 2048) -> Tuple[np.ndarray, np.ndarray]:
    """For each point, (distance in m, index) of the nearest target. Inf / -1 without targets."""
    n = len(points_lon)
    dist = np.full(n, np.inf)
    idx = np.full(n, -1, dtype=int)
    if n == 0 or len(targets_lon) == 0:
        return dist, idx
    chunk = max(1, min(chunk, MAX_PAIRS_PER_CHUNK // len(targets_lon)))
    tl = np.asarray(targets_lon, dtype="float64")[None, :]
    tb = np.asarray(targets_lat, dtype="float64")[None, :]
    for start in range(0, n, chunk):
        sl = slice(start, start + chunk)
        d = haversine_m(np.asarray(points_lon[sl])[:, None], np.asarray(points_lat[sl])[:, None], tl, tb)
        k = np.argmin(d, axis=1)
        idx[sl] = k
        dist[sl] = d[np.arange(len(k)), k]
    return dist, idx
