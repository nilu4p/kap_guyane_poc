"""Multi-source fusion of the built-up surface, cell by cell, 1985 → today.

| Period | Source | Role |
| --- | --- | --- |
| 1985 → 2015 | WSF Evolution (DLR, Landsat 30 m) | historical growth, every 5 years |
| 2019 | WSF 2019 (DLR, Sentinel-1/2 10 m) | **reference** built surface |
| 2016 → today | Sentinel-2 dry-season composites (computed here) | yearly change since the reference |
| today (mixed dates) | Microsoft building footprints | buildings per built hectare (to count) |

Fusion rules, per 200 m cell (fraction of the cell that is built, 0-1):

- **reference** ``F(2019) = WSF2019``;
- **after 2015** ``F(y) = clip(WSF2019 + Δ(y), 0, 1)`` with ``Δ(y) = S̃(y) − S̃(2019)``:
  Sentinel-2 only measures the *change* relative to the reference year, which cancels
  its own bias; ``S̃`` is the Sentinel-2 cell fraction smoothed by a 3-year running
  median (seasonal noise), undetermined years taking the nearest observed one;
  a change smaller than the **noise floor** τ is ignored — τ is the 95th percentile of
  |Δ| over invariant cells (never settled in WSF 2019 nor WSF Evolution), bounded to
  [0.05, 0.3]: without it, the positive noise of thousands of forest cells (the
  negative noise being clipped at 0) would add up to a fake growth; change is only
  kept **within 1 km of the existing settlement** (WSF 2019 / WSF Evolution), where
  the calibration is done too — isolated "built" pixels in rice fields, savannas or
  beaches are bare soils of the dry season, not new districts;
- **quality gate**: when the Sentinel-2 series disagrees with WSF 2019 on the settled
  neighbourhood (grade "faible", see :func:`satellite.grade`), it is **not applied**:
  the reference WSF 2019 stays for every year after 2016 and the commune is flagged;
- **1985 → 2015** ``F(y) = F(2016) × WSF-E(y) / WSF-E(2015)``: each cell keeps its
  own relative growth from the Landsat archive and joins its first Sentinel-2 value
  without a break (cells first settled after 2015 are 0 before);
- cells of the commune outside the Sentinel-2 windows (small remote villages) keep
  the reference value for every year after 2015 and are flagged as such.

The result is stored sparse (cells with some built surface only).
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.analyse import layers as layer_store
from app.analyse.grid import CELL_HA, Window, cell_id, mask_inside, parse_cell
from app.config import Settings, get_settings
from app.core.geo import bbox_of
from app.sources import msbuildings, wsf

logger = logging.getLogger(__name__)

BLOCK = 32               # cells per block side (6.4 km) when choosing where to read Sentinel-2
REFERENCE_YEAR = 2019
MIN_BLOCK_HA = 2.0       # a block is analysed when it holds at least this settled surface
TOWN_BLOCK_HA = 40.0     # around towns, the neighbouring blocks are analysed too (growth at the edge)


def _components(selected: Dict[Tuple[int, int], float]) -> List[List[Tuple[int, int]]]:
    """8-connected groups of selected blocks."""
    todo, groups = set(selected), []
    while todo:
        start = todo.pop()
        group, stack = [start], [start]
        while stack:
            r, c = stack.pop()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    n = (r + dr, c + dc)
                    if n in todo:
                        todo.remove(n)
                        group.append(n)
                        stack.append(n)
        groups.append(group)
    return groups


def analysis_windows(contour: Dict[str, Any], settings: Optional[Settings] = None) -> Tuple[List[Window], Dict[str, Any]]:
    """Where to read the satellite archives for a commune: its settled areas, not its forest.

    A quick look at WSF 2019 (overviews) over the whole commune finds the settled
    blocks; neighbouring blocks of towns are added (new districts grow at the edge);
    adjacent blocks are merged into rectangles; the largest settlements are kept up to
    ``max_analysis_area_km2``.
    """
    cfg = settings or get_settings()
    commune_window = Window.from_bbox(bbox_of(contour))
    inside = mask_inside(commune_window, contour)
    quick = wsf.settlement_2019(commune_window, cfg, quick=True) * inside
    settled: Dict[Tuple[int, int], float] = {}
    in_commune: set = set()
    for block in commune_window.blocks(BLOCK):
        i0, j0 = commune_window.index(block.row1, block.col0)
        rows, cols = block.shape
        key = ((block.row0 - commune_window.row0) // BLOCK, (block.col0 - commune_window.col0) // BLOCK)
        if inside[i0:i0 + rows, j0:j0 + cols].any():
            in_commune.add(key)
        ha = float(quick[i0:i0 + rows, j0:j0 + cols].sum()) * CELL_HA
        if ha > 0:
            settled[key] = ha
    selected = {k: v for k, v in settled.items() if v >= MIN_BLOCK_HA}
    for (r, c), ha in list(selected.items()):
        if ha >= TOWN_BLOCK_HA:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (r + dr, c + dc) in in_commune:  # never across the river into Suriname / Brazil
                        selected.setdefault((r + dr, c + dc), settled.get((r + dr, c + dc), 0.0))
    windows: List[Tuple[float, Window]] = []
    for group in _components(selected):
        rows = [r for r, _ in group]
        cols = [c for _, c in group]
        rect = Window(commune_window.row0 + min(rows) * BLOCK, commune_window.col0 + min(cols) * BLOCK,
                      min(commune_window.row0 + (max(rows) + 1) * BLOCK - 1, commune_window.row1),
                      min(commune_window.col0 + (max(cols) + 1) * BLOCK - 1, commune_window.col1))
        ha = sum(selected[g] for g in group)
        n_rect = (max(rows) - min(rows) + 1) * (max(cols) - min(cols) + 1)
        if n_rect > 3 * len(group):  # sparse, elongated group: keep its blocks separate
            for g in group:
                r0 = commune_window.row0 + g[0] * BLOCK
                c0 = commune_window.col0 + g[1] * BLOCK
                windows.append((selected[g], Window(r0, c0, min(r0 + BLOCK - 1, commune_window.row1),
                                                    min(c0 + BLOCK - 1, commune_window.col1))))
        else:
            windows.append((ha, rect))
    windows.sort(key=lambda t: -t[0])
    kept, area, skipped_ha = [], 0.0, 0.0
    for ha, window in windows:
        if area + window.area_km2 <= cfg.max_analysis_area_km2 or not kept:
            kept.append(window)
            area += window.area_km2
        else:
            skipped_ha += ha
    info = {
        "settled_ha_quick": round(float(quick.sum()) * CELL_HA, 1),
        "windows": [list(w.bbox) for w in kept],
        "area_km2": round(area, 1),
        "skipped_settled_ha": round(skipped_ha, 1),
    }
    return kept, info


def _smooth(years: List[int], values: List[Optional[np.ndarray]]) -> Dict[int, np.ndarray]:
    """3-year running median per cell, undetermined years filled from the nearest observed one."""
    stack = np.stack([v if v is not None else np.full_like(next(x for x in values if x is not None), np.nan) for v in values])
    filled = stack.copy()
    n = len(years)
    for k in range(n):  # nearest observed year for NaN cells
        missing = np.isnan(filled[k])
        if not missing.any():
            continue
        for dist in range(1, n):
            for kk in (k - dist, k + dist):
                if 0 <= kk < n:
                    src = stack[kk]
                    take = missing & np.isfinite(src)
                    filled[k][take] = src[take]
                    missing &= ~take
            if not missing.any():
                break
    out = {}
    for k, year in enumerate(years):
        lo, hi = max(0, k - 1), min(n, k + 2)
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            out[year] = np.nanmedian(filled[lo:hi], axis=0)
    return out


def isotonic(values: np.ndarray) -> np.ndarray:
    """Non-decreasing least-squares fit of each row (pool-adjacent-violators), rows = cells, columns = years."""
    out = values.astype("float64").copy()
    for r in range(out.shape[0]):
        row = out[r]
        if np.all(np.diff(row) >= 0):
            continue
        blocks: List[List[float]] = []  # [sum, count]
        for v in row:
            blocks.append([float(v), 1.0])
            while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
                total, count = blocks.pop()
                blocks[-1][0] += total
                blocks[-1][1] += count
        k = 0
        for total, count in blocks:
            n = int(count)
            row[k:k + n] = total / count
            k += n
    return out


def fuse(commune: str, contour: Dict[str, Any], settings: Optional[Settings] = None,
         progress: Optional[Callable[[str, int], None]] = None, with_sentinel2: bool = True,
         last_year: Optional[int] = None) -> Dict[str, Any]:
    """Compute and store the fused built-up layer of a commune; returns its summary."""
    from app.analyse import satellite
    import datetime

    cfg = settings or get_settings()
    step = progress or (lambda _m, _p: None)
    step("Repérage des zones habitées (WSF 2019, aperçu)", 2)
    windows, info = analysis_windows(contour, cfg)
    commune_window = Window.from_bbox(bbox_of(contour))
    inside = mask_inside(commune_window, contour)
    quick = wsf.settlement_2019(commune_window, cfg, quick=True) * inside

    step("Surface bâtie de référence 2019 (WSF 2019, 10 m)", 8)
    refs = [wsf.settlement_2019(w, cfg) for w in windows]
    step("Croissance historique 1985 → 2015 (WSF Evolution)", 14)
    evolutions: List[Optional[Dict[int, np.ndarray]]] = []
    for w in windows:
        try:
            evolutions.append(wsf.evolution(w, cfg))
        except wsf.WsfError as exc:
            logger.warning("WSF Evolution unavailable for %s: %s", commune, exc)
            evolutions.append(None)

    now_year = last_year or datetime.date.today().year
    # The current dry season is used only once it is over (end month passed).
    if datetime.date.today().month <= cfg.s2_season_end_month and not last_year:
        now_year -= 1
    s2_years = list(range(cfg.s2_first_year, now_year + 1))
    s2: Dict[str, Any] = {"years": {}, "water": [None] * len(windows), "calibration": None, "scenes": {}, "errors": {}}
    focus: List[Optional[np.ndarray]] = [None] * len(windows)
    if with_sentinel2 and windows:
        def s2_progress(message: str, pct: int) -> None:
            step(message, 20 + int(pct * 0.65))
        focus = [satellite.settled_focus(ref, (e or {}).get(2015)) for ref, e in zip(refs, evolutions)]
        try:
            s2 = satellite.series(windows, s2_years, refs, REFERENCE_YEAR, cfg, progress=s2_progress,
                                  stable=[(e or {}).get(2015) for e in evolutions], focus=focus)
        except satellite.SatelliteError as exc:
            s2["errors"]["all"] = str(exc)
            logger.warning("Sentinel-2 series unavailable for %s: %s", commune, exc)

    step("Fusion des sources et stockage (carreaux de 200 m)", 88)
    hist_years = list(wsf.EVOLUTION_YEARS)
    quality = satellite.grade(s2.get("calibration"))
    # A series that disagrees with WSF 2019 is not applied: the reference stays, and the meta says why.
    applied = quality["level"] in ("bonne", "moyenne")
    obs_years = sorted(int(y) for y in s2["years"] if any(a is not None for a in s2["years"][y])) if applied else []
    series_years = sorted(set(hist_years) | {REFERENCE_YEAR} | set(range(cfg.s2_first_year, now_year + 1)))
    series_years = [y for y in series_years if y <= 2015 or y >= cfg.s2_first_year]
    cells: Dict[str, List[float]] = {}
    covered: set = set()
    water_cells: Dict[str, float] = {}
    noise_floors: List[float] = []
    for k, window in enumerate(windows):
        ref = refs[k]
        win_inside = mask_inside(window, contour)
        fused: Dict[int, np.ndarray] = {REFERENCE_YEAR: ref}
        evo = evolutions[k]
        local_obs = [y for y in obs_years if s2["years"][y][k] is not None]
        if local_obs:
            smoothed = _smooth(local_obs, [s2["years"][y][k] for y in local_obs])
            # Growth curve of each cell: non-decreasing fit of the smoothed seasons (isotonic regression).
            stack = np.stack([smoothed[y] for y in local_obs], axis=-1)
            shape = stack.shape
            flat = stack.reshape(-1, len(local_obs))
            signal = flat.max(axis=1) > 0
            flat[signal] = isotonic(flat[signal])
            stack = flat.reshape(shape)
            smoothed = {y: stack[..., n] for n, y in enumerate(local_obs)}
            anchor_year = min(local_obs, key=lambda y: abs(y - REFERENCE_YEAR))
            anchor = smoothed[anchor_year]
            # Noise floor measured on invariant cells (never settled in either WSF product): a change
            # smaller than what forest cells "show" from one season to the next is not a change.
            veg = ref <= 0.0
            if evo is not None:
                veg &= evo[2015] <= 0.0
            deltas = np.concatenate([np.abs(smoothed[y] - anchor)[veg] for y in local_obs]) if veg.any() else np.array([])
            tau = float(np.clip(np.quantile(deltas, 0.95), 0.05, 0.3)) if deltas.size >= 100 else 0.1
            noise_floors.append(round(tau, 3))
            near = focus[k] if focus[k] is not None else np.ones(window.shape, dtype=bool)
            for y in range(cfg.s2_first_year, now_year + 1):
                nearest_obs = min(local_obs, key=lambda o: abs(o - y))
                delta = smoothed[nearest_obs] - anchor
                # Change kept above the noise floor and within 1 km of the existing settlement only.
                delta = np.where((np.abs(delta) >= tau) & near, delta, 0.0)
                fused[y] = np.clip(ref + delta, 0.0, 1.0)
        else:
            for y in range(cfg.s2_first_year, now_year + 1):
                fused.setdefault(y, ref)
        if evo:
            # Historical curve joined on the first Sentinel-2 year: each cell keeps its own relative
            # growth 1985 → 2015 (WSF Evolution) and meets its 2016 value without a break.
            join = fused.get(cfg.s2_first_year, ref)
            base = evo[2015]
            for y in hist_years:
                fused[y] = np.where(base > 0, join * evo[y] / np.maximum(base, 1e-6), 0.0)
        water = s2["water"][k] if s2["water"] and s2["water"][k] is not None else None
        rows, cols = window.shape
        for i in range(rows):
            for j in range(cols):
                if not win_inside[i, j]:
                    continue
                cid = cell_id(*window.cell_at(i, j))
                covered.add(cid)
                values = [round(float(fused[y][i, j]) if y in fused else 0.0, 3) for y in series_years]
                if water is not None and water[i, j] > 0.3:
                    water_cells[cid] = round(float(water[i, j]), 2)
                if max(values) >= 0.01:
                    cells[cid] = values
    # Settled cells of the commune outside the Sentinel-2 windows: reference value, flat.
    uncovered = 0
    for i, j in zip(*np.nonzero(quick >= 0.01)):
        cid = cell_id(*commune_window.cell_at(int(i), int(j)))
        if cid in covered:
            continue
        uncovered += 1
        v = round(float(quick[i, j]), 3)
        cells[cid] = [0.0 if y < cfg.s2_first_year else v for y in series_years]

    step("Empreintes de bâtiments (Microsoft) agrégées par carreau", 93)
    buildings: Dict[str, List[float]] = {}
    buildings_error = None
    try:
        all_cells = msbuildings.cells_in(bbox_of(contour), cfg)
        for cid, value in all_cells.items():
            r, c = parse_cell(cid)
            if commune_window.row0 <= r <= commune_window.row1 and commune_window.col0 <= c <= commune_window.col1:
                i, j = commune_window.index(r, c)
                if inside[i, j]:
                    buildings[cid] = value
    except msbuildings.BuildingsError as exc:
        buildings_error = str(exc)

    ref_idx = series_years.index(REFERENCE_YEAR)
    totals = {str(y): round(sum(v[n] for v in cells.values()) * CELL_HA, 1) for n, y in enumerate(series_years)}
    # Buildings per built hectare where both products see something (to turn hectares into buildings).
    num = sum(buildings[c][0] for c in buildings if c in cells and cells[c][ref_idx] > 0.05)
    den = sum(cells[c][ref_idx] * CELL_HA for c in buildings if c in cells and cells[c][ref_idx] > 0.05)
    per_ha = round(num / den, 1) if den > 0 else None
    meta = {
        "years": series_years,
        "reference_year": REFERENCE_YEAR,
        "observed_years": obs_years,
        "windows": info,
        "calibration": s2.get("calibration"),
        "quality": quality,
        "sentinel2_applied": applied,
        "scenes": {str(k): v for k, v in (s2.get("scenes") or {}).items()},
        "errors": s2.get("errors") or {},
        "uncovered_cells": uncovered,
        "noise_floor": noise_floors,
        "series_break": {"between": [2015, cfg.s2_first_year],
                         "reason": "Changement de capteur : WSF Evolution (Landsat 30 m) jusqu'en 2015, puis Sentinel-2 recalé sur "
                                   "WSF 2019 (10 m). L'habitat diffus et les petites constructions, invisibles à 30 m, apparaissent "
                                   "en 2016 : l'écart entre 2015 et 2016 n'est pas une croissance."},
        "totals_ha": totals,
        "buildings_per_built_ha": per_ha,
        "buildings_total": int(sum(v[0] for v in buildings.values())),
        "buildings_error": buildings_error,
        "sources": ["DLR WSF Evolution 1985-2015", "DLR WSF 2019", "Copernicus Sentinel-2 L2A (Earth Search)",
                    "Microsoft Global ML Building Footprints"],
    }
    layer_store.save(commune, "builtup", {"years": series_years, "cells": cells}, meta, cfg)
    layer_store.save(commune, "water", water_cells, {"source": "Sentinel-2 SCL + MNDWI"}, cfg)
    layer_store.save(commune, "buildings", buildings, {"source": "Microsoft Global ML Building Footprints",
                                                      "note": "comptes agrégés par carreau, aucune emprise conservée"}, cfg)
    step("Terminé", 100)
    return meta


def load(commune: str, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    stored = layer_store.load(commune, "builtup", settings)
    if stored is None:
        return None
    payload, meta, computed_at = stored
    return {"years": payload["years"], "cells": payload["cells"], "meta": meta, "computed_at": computed_at}


def year_values(data: Dict[str, Any], year: int) -> Dict[str, float]:
    """Built fraction of each cell at ``year`` (nearest year of the series)."""
    years = data["years"]
    k = min(range(len(years)), key=lambda n: (abs(years[n] - year), -years[n]))
    return {cid: v[k] for cid, v in data["cells"].items() if v[k] > 0}


def growth(data: Dict[str, Any], start: int, end: int) -> Dict[str, float]:
    """Built hectares gained (or lost) per cell between two years."""
    a, b = year_values(data, start), year_values(data, end)
    out = {}
    for cid in set(a) | set(b):
        delta = (b.get(cid, 0.0) - a.get(cid, 0.0)) * CELL_HA
        if abs(delta) >= 0.01:
            out[cid] = round(delta, 3)
    return out


def nearest_year(years: Sequence[int], year: int) -> int:
    return min(years, key=lambda y: (abs(y - year), -y))


def to_ha(fraction: float) -> float:
    return fraction * CELL_HA if math.isfinite(fraction) else 0.0
