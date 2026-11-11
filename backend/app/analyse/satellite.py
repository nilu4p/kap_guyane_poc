"""Built-up surface from Sentinel-2, year after year, on the 200 m grid.

Method (documented in the knowledge base, *Moteur › Analyse satellitaire*):

1. **Scenes** — Sentinel-2 L2A (Earth Search, AWS open data, keyless) of the dry
   season (August → December by default), under a cloud ceiling; the clearest
   ``s2_scenes_per_year`` acquisitions of each MGRS tile are kept.
2. **Composite** — bands B11 (SWIR 1.6 µm), B8A (NIR), B4 (red), B3 (green) and the
   scene classification (SCL) are resampled to 20 m on a sub-grid aligned with the 200 m
   cells (10 × 10 pixels per cell). Clouds, shadows, cirrus and no-data are masked
   with SCL; for every pixel the *median* over the clear observations of the season
   gives NDBI = (B11 − B8A) / (B11 + B8A) and NDVI = (B8A − B4) / (B8A + B4).
3. **Built score** — s = NDBI − NDVI (roofs, concrete, laterite tracks score high,
   vegetation low). Water is excluded when SCL says so *or* when MNDWI =
   (B3 − B11) / (B3 + B11) > 0.1: the turbid, sediment-laden rivers of Guiana (Maroni,
   Oyapock, Mahury) are often missed by SCL alone.
4. **Calibration** — the threshold *t* is chosen on the reference year so that the
   built surface measured by Sentinel-2 equals the WSF 2019 (DLR) built surface over
   the same area (quantile matching). The agreement between both products, cell by
   cell, is reported (correlation, concordance of built / not built cells): it is
   the quality figure shown with every result.
   **Harmonisation** — seasons differ (rain, sun angle, dryness of bare soils), so the
   same *t* would make whole towns "grow" or "shrink" from one year to the next. Each
   season is normalised linearly on two pseudo-invariant targets — the stable built
   core (≥ 60 % built in WSF 2019 and already in 2015) and the stable vegetation (never
   settled) — before the reference threshold is applied.
5. **Cell fraction** — share of the cell's valid pixels with s > t. A cell with
   less than 30 % valid pixels in a season is left undetermined for that year
   (filled from the neighbouring years when the series is fused).

Nothing finer than the 200 m cell is kept: the 20 m pixels only live in memory.
"""

from __future__ import annotations

import datetime
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.analyse.grid import DLAT, DLON, Window
from app.config import Settings, get_settings
from app.sources import health
from app.sources.http import USER_AGENT

logger = logging.getLogger(__name__)

SUB = 10  # sub-pixels per cell side (20 m)
COLLECTION = "sentinel-2-l2a"
BANDS = ("swir16", "nir08", "red", "green", "scl")
HREF = re.compile(r"^https://sentinel-cogs\.s3\.us-west-2\.amazonaws\.com/[A-Za-z0-9/_.-]+\.tif$")
INVALID_SCL = (0, 1, 2, 3, 8, 9, 10)  # no data, saturated, dark / shadow, cloud shadow, clouds, cirrus
WATER_SCL = 6
MIN_VALID_SHARE = 0.3
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2")


class SatelliteError(RuntimeError):
    pass


@dataclass
class Composite:
    year: int
    window: Window
    score: np.ndarray            # (rows*SUB, cols*SUB) built score s, NaN where no clear observation
    water: np.ndarray            # same shape, bool
    scenes: List[Dict[str, Any]] = field(default_factory=list)

    def valid_share(self) -> float:
        return float(np.isfinite(self.score).mean()) if self.score.size else 0.0


# --------------------------------------------------------------------------- catalogue


def search(bbox: Sequence[float], year: int, cfg: Settings) -> List[Dict[str, Any]]:
    """Clearest dry-season scenes of ``year`` over ``bbox`` (best N per MGRS tile)."""
    import httpx

    start = datetime.date(year, cfg.s2_season_start_month, 1)
    end_month = cfg.s2_season_end_month
    end = datetime.date(year + (end_month == 12), 1 if end_month == 12 else end_month + 1, 1)
    body = {
        "collections": [COLLECTION], "bbox": list(bbox), "limit": 200,
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T00:00:00Z",
        "query": {"eo:cloud_cover": {"lt": cfg.s2_max_cloud}},
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
    }
    try:
        response = httpx.post(f"{cfg.stac_url}/search", json=body, headers={"User-Agent": USER_AGENT},
                              timeout=max(cfg.http_timeout, 60.0))
        response.raise_for_status()
        items = response.json().get("features") or []
    except Exception as exc:
        health.record("sentinel2", False, type(exc).__name__)
        raise SatelliteError(f"catalogue Sentinel-2 injoignable ({type(exc).__name__})") from exc
    health.record("sentinel2", True)
    per_tile: Dict[str, List[Dict[str, Any]]] = {}
    seen = set()
    for item in items:
        props = item.get("properties") or {}
        tile = str(props.get("grid:code") or item["id"].split("_")[1])
        acquisition = (tile, (props.get("datetime") or "")[:10])
        if acquisition in seen or not all(b in (item.get("assets") or {}) for b in BANDS):
            continue  # the same acquisition re-processed (…_0_L2A / …_1_L2A) counts once
        seen.add(acquisition)
        bucket = per_tile.setdefault(tile, [])
        if len(bucket) < cfg.s2_scenes_per_year:
            bucket.append(item)
    return [i for bucket in per_tile.values() for i in bucket]


def _band(item: Dict[str, Any], band: str) -> Tuple[str, float, float]:
    meta = (item.get("assets") or {}).get(band) or {}
    href = meta.get("href") or ""
    if not HREF.match(href):
        raise SatelliteError(f"bande {band} hors de l'archive publique Sentinel-2")
    if band == "scl":
        return href, 1.0, 0.0
    info = (meta.get("raster:bands") or [{}])[0]
    scale = float(info.get("scale", 1e-4))
    offset = float(info.get("offset", 0.0))
    if (item.get("properties") or {}).get("earthsearch:boa_offset_applied"):
        offset = 0.0  # Earth Search already removed the +1000 DN offset (processing baseline ≥ 04.00)
    return href, scale, offset


def _read(href: str, window: Window, nearest: bool, cfg: Settings) -> np.ndarray:
    """One band resampled to the 20 m sub-grid of ``window`` (0 = no data)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT

    rows, cols = window.shape
    west, _, _, north = window.bbox
    transform = from_origin(west, north, DLON / SUB, DLAT / SUB)
    with rasterio.Env(**GDAL_ENV, GDAL_HTTP_TIMEOUT=str(int(cfg.http_timeout))):
        with rasterio.open(href) as src, WarpedVRT(
            src, crs="EPSG:4326", transform=transform, width=cols * SUB, height=rows * SUB,
            resampling=Resampling.nearest if nearest else Resampling.average, nodata=0,
        ) as vrt:
            return vrt.read(1)


def composite(window: Window, items: List[Dict[str, Any]], year: int, cfg: Settings) -> Composite:
    """Median built score of the clear observations of the season over ``window``."""
    if not items:
        raise SatelliteError(f"aucune scène Sentinel-2 exploitable en saison sèche {year}")
    jobs = []
    for item in items:
        for band in BANDS:
            href, scale, offset = _band(item, band)
            jobs.append((item["id"], band, href, scale, offset))

    def run(job: Tuple[str, str, str, float, float]) -> Tuple[str, str, Optional[np.ndarray], float, float]:
        item_id, band, href, scale, offset = job
        try:
            return item_id, band, _read(href, window, band == "scl", cfg), scale, offset
        except Exception as exc:
            logger.warning("Sentinel-2 %s %s unreadable: %s", item_id, band, type(exc).__name__)
            return item_id, band, None, scale, offset

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(run, jobs))
    by_item: Dict[str, Dict[str, Tuple[np.ndarray, float, float]]] = {}
    for item_id, band, data, scale, offset in results:
        if data is not None:
            by_item.setdefault(item_id, {})[band] = (data, scale, offset)
    scores, waters, used = [], [], []
    for item in items:
        bands = by_item.get(item["id"], {})
        if len(bands) < len(BANDS):
            continue
        scl = bands["scl"][0]
        refl = {}
        for name in ("swir16", "nir08", "red", "green"):
            data, scale, offset = bands[name]
            refl[name] = np.where(data > 0, data.astype("float32") * scale + offset, np.nan)
        clear = ~np.isin(scl, INVALID_SCL)
        for name in refl:
            clear &= np.isfinite(refl[name])
        if clear.mean() < 0.01:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            ndbi = (refl["swir16"] - refl["nir08"]) / (refl["swir16"] + refl["nir08"])
            ndvi = (refl["nir08"] - refl["red"]) / (refl["nir08"] + refl["red"])
            mndwi = (refl["green"] - refl["swir16"]) / (refl["green"] + refl["swir16"])
        is_water = (scl == WATER_SCL) | (np.nan_to_num(mndwi, nan=-1) > 0.1)
        score = np.where(clear, ndbi - ndvi, np.nan).astype("float32")
        scores.append(score)
        waters.append(np.where(clear, is_water, np.nan).astype("float32"))
        props = item.get("properties") or {}
        used.append({"id": item["id"], "date": (props.get("datetime") or "")[:10],
                     "cloud": round(float(props.get("eo:cloud_cover") or 0), 1), "clear_share": round(float(clear.mean()), 3)})
    if not scores:
        raise SatelliteError(f"scènes {year} illisibles ou entièrement nuageuses sur la zone")
    stack = np.stack(scores)
    with np.errstate(all="ignore"):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            median = np.nanmedian(stack, axis=0)
            water = np.nanmean(np.stack(waters), axis=0) > 0.5
    return Composite(year=year, window=window, score=median.astype("float32"), water=water, scenes=used)


# --------------------------------------------------------------------------- cells & calibration


def _blocks(a: np.ndarray, shape: Tuple[int, int]) -> np.ndarray:
    rows, cols = shape
    return a.reshape(rows, SUB, cols, SUB)


def cell_fraction(comp: Composite, threshold: float) -> Tuple[np.ndarray, np.ndarray]:
    """(built fraction per cell — NaN when undetermined, water fraction per cell)."""
    shape = comp.window.shape
    valid = np.isfinite(comp.score) & ~comp.water
    built = valid & (np.nan_to_num(comp.score, nan=-9) > threshold)
    n_valid = _blocks(valid, shape).sum(axis=(1, 3))
    n_built = _blocks(built, shape).sum(axis=(1, 3))
    observed = _blocks(np.isfinite(comp.score), shape).sum(axis=(1, 3))
    water = _blocks(comp.water & np.isfinite(comp.score), shape).sum(axis=(1, 3)) / np.maximum(observed, 1)
    frac = np.where(observed >= MIN_VALID_SHARE * SUB * SUB, n_built / np.maximum(n_valid, 1), np.nan)
    frac = np.where(water > 0.9, 0.0, frac)  # open water: nothing built, never undetermined
    return frac, water


def _sub(mask: np.ndarray) -> np.ndarray:
    return np.repeat(np.repeat(mask, SUB, axis=0), SUB, axis=1)


def dilate(mask: np.ndarray, radius_cells: int) -> np.ndarray:
    """Cells within ``radius_cells`` (Chebyshev) of a True cell."""
    out = mask.copy()
    rows, cols = mask.shape
    for di in range(-radius_cells, radius_cells + 1):
        for dj in range(-radius_cells, radius_cells + 1):
            src = mask[max(0, di):rows + min(0, di), max(0, dj):cols + min(0, dj)]
            out[max(0, -di):rows + min(0, -di), max(0, -dj):cols + min(0, -dj)] |= src
    return out


def settled_focus(ref: np.ndarray, stable: Optional[np.ndarray] = None, radius_cells: int = 5) -> np.ndarray:
    """Neighbourhood of the existing settlement (≤ 1 km of a WSF built cell): where growth is measured."""
    seed = ref >= 0.05
    if stable is not None:
        seed |= stable >= 0.05
    return dilate(seed, radius_cells)


def calibrate(comps: Sequence[Composite], references: Sequence[np.ndarray],
              focus: Optional[Sequence[Optional[np.ndarray]]] = None) -> Dict[str, Any]:
    """Threshold matching the WSF 2019 built surface + cell agreement figures (on the settled neighbourhood)."""
    scores, ref_area, total = [], 0.0, 0.0
    focus = list(focus) if focus is not None else [None] * len(comps)
    for comp, ref, area in zip(comps, references, focus):
        valid = np.isfinite(comp.score) & ~comp.water
        if area is not None:
            valid &= _sub(area)
        scores.append(comp.score[valid])
        cells_valid = _blocks(valid, comp.window.shape).mean(axis=(1, 3))
        ref_area += float((ref * cells_valid).sum())
        total += float(cells_valid.sum())
    values = np.concatenate(scores) if scores else np.array([])
    if values.size < 1000 or total <= 0:
        raise SatelliteError("trop peu de pixels clairs pour calibrer l'année de référence")
    share = min(max(ref_area / total, 0.001), 0.95)
    threshold = float(np.quantile(values, 1.0 - share))
    xs, ys = [], []
    for comp, ref, area in zip(comps, references, focus):
        frac, _water = cell_fraction(comp, threshold)
        keep = np.isfinite(frac)
        if area is not None:
            keep &= area
        xs.append(frac[keep])
        ys.append(ref[keep])
    x, y = np.concatenate(xs), np.concatenate(ys)
    # Cells empty in both products (forest, savanna) are trivially concordant: the figures are
    # computed on the cells where at least one product sees some built surface.
    seen = (x > 0.05) | (y > 0.05)
    x, y = x[seen], y[seen]
    corr = float(np.corrcoef(x, y)[0, 1]) if x.size > 2 and x.std() > 0 and y.std() > 0 else None
    built_s2, built_ref = x > 0.2, y > 0.2
    agree = float((built_s2 == built_ref).mean()) if x.size else None
    tp = float((built_s2 & built_ref).sum())
    precision = tp / max(float(built_s2.sum()), 1.0)
    recall = tp / max(float(built_ref.sum()), 1.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": round(threshold, 4), "reference_share": round(share, 4),
        "cells_compared": int(x.size), "correlation": round(corr, 3) if corr is not None else None,
        "concordance": round(agree, 3) if agree is not None else None, "f1_built": round(f1, 3),
        "precision": round(precision, 3), "recall": round(recall, 3),
    }


def invariant_masks(ref: np.ndarray, stable: Optional[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    """Sub-pixel masks of pseudo-invariant targets: stable built core and stable vegetation.

    Core: cells ≥ 60 % built in WSF 2019 (and already ≥ 60 % in 2015 when WSF Evolution is
    known). Vegetation: cells with no settlement at all in either product.
    """
    core = ref >= 0.6
    veg = ref <= 0.0
    if stable is not None:
        core &= stable >= 0.6
        veg &= stable <= 0.0
    return _sub(core), _sub(veg)


def _median(comps: Sequence[Composite], masks: Sequence[np.ndarray]) -> Optional[float]:
    values = [c.score[m & np.isfinite(c.score) & ~c.water] for c, m in zip(comps, masks)]
    values = np.concatenate(values) if values else np.array([])
    return float(np.median(values)) if values.size >= 2000 else None


def harmonised_threshold(comps: Sequence[Composite], cores: Sequence[np.ndarray], vegs: Sequence[np.ndarray],
                         ref_core: float, ref_veg: float, ref_threshold: float) -> Optional[float]:
    """Threshold of this season after a two-point linear normalisation on invariant targets.

    The season's scores are mapped by s' = a·s + b so that the medians of the stable core
    and of the stable vegetation equal those of the reference season; the reference
    threshold applied to s' is the threshold (t − b) / a applied to the raw scores.
    """
    core, veg = _median(comps, cores), _median(comps, vegs)
    if core is None or veg is None or core - veg < 0.05 or ref_core - ref_veg < 0.05:
        return None  # targets too small, too cloudy or not separable: keep the reference threshold
    a = (ref_core - ref_veg) / (core - veg)
    b = ref_core - a * core
    return (ref_threshold - b) / a


def series(windows: Sequence[Window], years: Sequence[int], references: Sequence[np.ndarray],
           reference_year: int = 2019, settings: Optional[Settings] = None,
           progress: Optional[Callable[[str, int], None]] = None,
           stable: Optional[Sequence[Optional[np.ndarray]]] = None,
           focus: Optional[Sequence[Optional[np.ndarray]]] = None) -> Dict[str, Any]:
    """Built fraction per cell for every year, per window, calibrated on ``reference_year``.

    Returns ``{"years": {year: [array per window or None]}, "water": [...], "calibration": {...},
    "scenes": {year: [...]}, "errors": {year: message}}``.
    """
    cfg = settings or get_settings()
    union = (min(w.bbox[0] for w in windows), min(w.bbox[1] for w in windows),
             max(w.bbox[2] for w in windows), max(w.bbox[3] for w in windows))
    composites: Dict[int, List[Optional[Composite]]] = {}
    scenes: Dict[int, List[Dict[str, Any]]] = {}
    errors: Dict[int, str] = {}
    ordered = [reference_year] + [y for y in years if y != reference_year]
    for n, year in enumerate(ordered):
        if progress:
            progress(f"Sentinel-2 saison sèche {year}", int(100 * n / max(len(ordered), 1)))
        try:
            items = search(union, year, cfg)
        except SatelliteError as exc:
            errors[year] = str(exc)
            composites[year] = [None] * len(windows)
            continue
        row: List[Optional[Composite]] = []
        for window in windows:
            west, south, east, north = window.bbox
            local = [i for i in items if _intersects(i.get("bbox"), (west, south, east, north))]
            try:
                row.append(composite(window, local, year, cfg))
            except SatelliteError as exc:
                errors[year] = str(exc)
                row.append(None)
        composites[year] = row
        scenes[year] = [s for c in row if c for s in c.scenes]
    # Calibrate on the reference year, or on the closest year that was observed.
    calib_year = next((y for y in sorted(composites, key=lambda y: abs(y - reference_year))
                       if all(c is not None for c in composites[y])), None)
    if calib_year is None:
        raise SatelliteError("aucune saison sèche exploitable pour calibrer l'indice de bâti")
    calibration = calibrate(composites[calib_year], references, focus)
    calibration["year"] = calib_year
    # Two-point radiometric harmonisation of the other seasons on pseudo-invariant targets.
    masks = [invariant_masks(ref, (stable or [None] * len(windows))[k]) for k, ref in enumerate(references)]
    cores, vegs = [m[0] for m in masks], [m[1] for m in masks]
    ref_core, ref_veg = _median(composites[calib_year], cores), _median(composites[calib_year], vegs)
    thresholds: Dict[int, float] = {calib_year: calibration["threshold"]}
    for year, row in composites.items():
        if year == calib_year:
            continue
        present = [k for k, c in enumerate(row) if c is not None]
        t = None
        if present and ref_core is not None and ref_veg is not None:
            t = harmonised_threshold([row[k] for k in present], [cores[k] for k in present], [vegs[k] for k in present],
                                     ref_core, ref_veg, calibration["threshold"])
        thresholds[year] = round(t, 4) if t is not None else calibration["threshold"]
    calibration["invariants"] = {"core_median": round(ref_core, 4) if ref_core is not None else None,
                                 "vegetation_median": round(ref_veg, 4) if ref_veg is not None else None}
    calibration["thresholds"] = {str(y): v for y, v in sorted(thresholds.items())}
    out_years: Dict[int, List[Optional[np.ndarray]]] = {}
    water: List[Optional[np.ndarray]] = [None] * len(windows)
    for year, row in composites.items():
        arrays: List[Optional[np.ndarray]] = []
        for k, comp in enumerate(row):
            if comp is None:
                arrays.append(None)
                continue
            frac, wat = cell_fraction(comp, thresholds.get(year, calibration["threshold"]))
            arrays.append(frac)
            water[k] = wat if water[k] is None else np.fmax(water[k], wat)
        out_years[year] = arrays
    return {"years": out_years, "water": water, "calibration": calibration, "scenes": scenes,
            "errors": {str(k): v for k, v in errors.items()}}


def _intersects(bbox: Optional[Sequence[float]], other: Sequence[float]) -> bool:
    if not bbox or len(bbox) < 4:
        return True
    return not (bbox[2] < other[0] or bbox[0] > other[2] or bbox[3] < other[1] or bbox[1] > other[3])


def grade(calibration: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Plain-language quality of a commune's Sentinel-2 series, from its agreement with WSF 2019.

    Computed on the settled neighbourhood (cells within 1 km of the 2019 settlement): F1 of the
    built / not built classification of the cells, and number of cells compared.
    """
    if not calibration:
        return {"level": "absente", "label": "Série Sentinel-2 non calculée",
                "advice": "Seules les références WSF 2019 / WSF Evolution sont disponibles."}
    f1 = calibration.get("f1_built") or 0.0
    cells = calibration.get("cells_compared") or 0
    if f1 >= 0.6 and cells >= 200:
        return {"level": "bonne", "label": "Accord satisfaisant avec WSF 2019",
                "advice": "Tendances exploitables ; contrôle visuel d'un échantillon de carreaux recommandé avant décision."}
    if f1 >= 0.45 and cells >= 100:
        return {"level": "moyenne", "label": "Accord partiel avec WSF 2019",
                "advice": "Tendances indicatives : confirmer les carreaux clés sur image très haute résolution (Pléiades, SEAS Guyane)."}
    return {"level": "faible", "label": "Accord insuffisant avec WSF 2019",
            "advice": "Bâti trop petit, trop dispersé ou confondu avec des sols nus : la croissance après 2019 n'est pas appliquée, "
                      "la référence WSF 2019 est conservée. Contrôle visuel sur image très haute résolution nécessaire."}
