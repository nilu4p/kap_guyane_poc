"""World Settlement Footprint (DLR, CC BY 4.0) read onto the 200 m grid, keyless.

- **WSF 2019** — settlement extent at 10 m from Sentinel-1 + Sentinel-2 (2019):
  value 255 = settlement, 0 = none. Our reference year for built-up surface.
- **WSF Evolution** — year (1985 → 2015) a 30 m pixel was first settled, from
  the Landsat archive: the historical growth curve of every neighbourhood.

Both are 2° × 2° Cloud-Optimised GeoTIFFs in EPSG:4326 published on the DLR
geoservice; only the windows needed are read (HTTP range requests). A window
crossing tile edges is assembled from every tile it touches.
"""

from __future__ import annotations

import logging
import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.analyse.grid import Window
from app.config import Settings, get_settings
from app.sources import health

logger = logging.getLogger(__name__)

EVOLUTION_YEARS = (1985, 1990, 1995, 2000, 2005, 2010, 2015)
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="TRUE")


class WsfError(RuntimeError):
    pass


def tiles(bbox: Sequence[float]) -> List[Tuple[int, int]]:
    """Lower-left corners (lon, lat) of the 2° tiles intersecting ``bbox``."""
    west, south, east, north = bbox
    lons = range(int(math.floor(west / 2) * 2), int(math.floor(east / 2) * 2) + 1, 2)
    lats = range(int(math.floor(south / 2) * 2), int(math.floor(north / 2) * 2) + 1, 2)
    return [(lo, la) for lo in lons for la in lats]


def tile_url(kind: str, lon: int, lat: int, cfg: Settings) -> str:
    if kind == "wsf2019":
        return f"{cfg.wsf2019_url}/WSF2019_v1_{lon}_{lat}.tif"
    return f"{cfg.wsf_evolution_url}/WSFevolution_v1_{lon}_{lat}.tif"


def _accumulate(kind: str, window: Window, cfg: Settings, layers: Callable[[np.ndarray], Dict[str, np.ndarray]],
                decimate: bool) -> Dict[str, np.ndarray]:
    """Read every tile part under ``window``, turn it into 0-1 layers, average them onto the grid."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject
    from rasterio.windows import from_bounds

    west, south, east, north = window.bbox
    out: Dict[str, np.ndarray] = {}
    read_any = False
    errors = []
    with rasterio.Env(**GDAL_ENV, GDAL_HTTP_TIMEOUT=str(int(cfg.http_timeout))):
        for lon, lat in tiles(window.bbox):
            url = tile_url(kind, lon, lat, cfg)
            part = (max(west, lon), max(south, lat), min(east, lon + 2), min(north, lat + 2))
            if part[0] >= part[2] or part[1] >= part[3]:
                continue
            try:
                with rasterio.open(url) as src:
                    src_window = from_bounds(*part, transform=src.transform).round_offsets().round_lengths()
                    if src_window.width < 1 or src_window.height < 1:
                        continue
                    shape = None
                    if decimate:  # quick look: ~4 source pixels per grid cell, overviews do the rest
                        rows, cols = window.shape
                        fx = (part[2] - part[0]) / (east - west)
                        fy = (part[3] - part[1]) / (north - south)
                        shape = (max(1, int(rows * fy * 2)), max(1, int(cols * fx * 2)))
                    data = src.read(1, window=src_window, out_shape=shape, boundless=False)
                    src_transform = src.window_transform(src_window)
                    if shape is not None:
                        src_transform = src_transform * src_transform.scale(src_window.width / shape[1], src_window.height / shape[0])
            except Exception as exc:
                errors.append(f"{url.rsplit('/', 1)[-1]}: {type(exc).__name__}")
                continue
            read_any = True
            for name, layer in layers(data).items():
                dst = np.full(window.shape, np.nan, dtype="float32")
                reproject(source=layer.astype("float32"), destination=dst, src_transform=src_transform,
                          src_crs="EPSG:4326", dst_transform=window.transform(), dst_crs="EPSG:4326",
                          resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
                out[name] = dst if name not in out else np.fmax(out[name], dst)
    if not read_any:
        health.record(f"dlr_{kind}", False, "; ".join(errors)[:200] or "aucune tuile")
        raise WsfError(f"{kind} illisible ({'; '.join(errors) or 'hors couverture'})")
    health.record(f"dlr_{kind}", True)
    return {name: np.nan_to_num(array, nan=0.0) for name, array in out.items()}


def settlement_2019(window: Window, settings: Optional[Settings] = None, quick: bool = False) -> np.ndarray:
    """Settled fraction (0-1) of each cell in 2019. ``quick`` reads the overviews (block selection only)."""
    cfg = settings or get_settings()
    layers = _accumulate("wsf2019", window, cfg, lambda d: {"f": (d == 255).astype("float32")}, decimate=quick)
    return layers["f"]


def evolution(window: Window, settings: Optional[Settings] = None,
              years: Sequence[int] = EVOLUTION_YEARS) -> Dict[int, np.ndarray]:
    """Settled fraction (0-1) of each cell at each year of ``years`` (cumulative since 1985)."""
    cfg = settings or get_settings()

    def split(data: np.ndarray) -> Dict[str, np.ndarray]:
        settled = data > 0
        return {str(y): (settled & (data <= y)).astype("float32") for y in years}

    layers = _accumulate("wsf_evolution", window, cfg, split, decimate=False)
    return {int(k): v for k, v in layers.items()}
