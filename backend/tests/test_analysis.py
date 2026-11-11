"""Spatial analysis on synthetic layers: fusion, calibration, population, accessibility, siting, watch, secrecy."""

from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
import pytest

from app.analyse import access, builtup, grid, layers as layer_store, population, satellite, watch
from app.territoire import store

COMMUNE = "97311"
CORE = (5.500, -54.030)       # existing town centre with a school
GROWTH = (5.470, -54.000)     # new district ~4.6 km away, no school
YEARS = [1985, 1990, 1995, 2000, 2005, 2010, 2015] + list(range(2016, 2026))


def _block(center: Any, size: int) -> List[str]:
    row, col = grid.cell_of(center[1], center[0])
    return [grid.cell_id(row + dr, col + dc) for dr in range(size) for dc in range(size)]


def seed_commune(settings: Any = None) -> Dict[str, List[str]]:
    """A commune with a dense core and a district built from scratch after 2019."""
    store.ensure_communes(settings)
    core, district = _block(CORE, 5), _block(GROWTH, 4)
    cells: Dict[str, List[float]] = {}
    for cid in core:
        cells[cid] = [0.5 if y < 2016 else 0.8 for y in YEARS]
    for cid in district:
        cells[cid] = [0.0 if y <= 2019 else round(min(0.6, 0.1 * (y - 2019)), 3) for y in YEARS]
    layer_store.save(COMMUNE, "builtup", {"years": YEARS, "cells": cells},
                     {"years": YEARS, "reference_year": 2019, "buildings_per_built_ha": 25.0,
                      "calibration": {"correlation": 0.7, "f1_built": 0.7, "cells_compared": 500, "concordance": 0.9},
                      "totals_ha": {}}, settings)
    layer_store.save(COMMUNE, "water", {}, {}, settings)
    layer_store.save(COMMUNE, "roads", core + district, {}, settings)
    store.replace_indicators([
        (COMMUNE, "population", 2023, 54429, "DS_POPULATIONS_HISTORIQUES"),
        (COMMUNE, "population", 2017, 42612, "DS_POPULATIONS_HISTORIQUES"),
        (COMMUNE, "rp_pop_total", 2023, 50000, "DS_RP_POPULATION_PRINC"),
        (COMMUNE, "rp_pop_moins_15", 2023, 20750, "DS_RP_POPULATION_PRINC"),
        (COMMUNE, "rp_age_2_5", 2023, 4000, "DS_RP_EDUCATION_PRINC"),
        (COMMUNE, "rp_age_6_10", 2023, 6000, "DS_RP_EDUCATION_PRINC"),
        (COMMUNE, "rp_age_11_14", 2023, 4000, "DS_RP_EDUCATION_PRINC"),
        (COMMUNE, "rp_age_15_17", 2023, 2500, "DS_RP_EDUCATION_PRINC"),
        (COMMUNE, "ecoles_pub_eleves", 2025, 12256, "EDUCATION_EFFECTIFS"),
        (COMMUNE, "ecoles_pub_classes", 2025, 648, "EDUCATION_EFFECTIFS"),
        ("973", "population", 2023, 293996, "DS_POPULATIONS_HISTORIQUES"),
        ("973", "rp_pop_total", 2023, 280000, "DS_RP_POPULATION_PRINC"),
        ("973", "rp_pop_moins_15", 2023, 89600, "DS_RP_POPULATION_PRINC"),
    ], settings)
    store.upsert_equipments([{"uid": "uai:TEST", "category": "ecole", "name": "École du centre", "commune": COMMUNE,
                              "lat": CORE[0] + 0.004, "lon": CORE[1] + 0.004, "capacity": 300.0, "capacity_unit": "élèves inscrits"}],
                            "education_nationale", settings=settings)
    return {"core": core, "district": district}


def test_isotonic_and_smoothing() -> None:
    fitted = builtup.isotonic(np.array([[0.5, 0.3, 0.4, 0.6, 0.55, 0.7]]))
    assert np.all(np.diff(fitted[0]) >= -1e-12) and abs(fitted[0].mean() - np.mean([0.5, 0.3, 0.4, 0.6, 0.55, 0.7])) < 1e-9
    a, b, c = np.array([[0.1]]), np.array([[np.nan]]), np.array([[0.9]])
    smoothed = builtup._smooth([2017, 2018, 2019], [a, b, c])
    # The undetermined year takes its nearest observed neighbour, then the 3-year median applies.
    assert smoothed[2018][0, 0] == pytest.approx(0.1) and np.isfinite(smoothed[2019][0, 0])


def test_calibration_matches_reference_surface_and_grades_quality() -> None:
    w = grid.Window.from_bbox((-54.05, 5.45, -54.00, 5.50))
    rows, cols = w.shape
    rng = np.random.default_rng(1)
    ref = np.zeros(w.shape)
    ref[: rows // 3, : cols // 3] = rng.uniform(0.2, 1.0, (rows // 3, cols // 3))
    sub = np.repeat(np.repeat(ref, satellite.SUB, 0), satellite.SUB, 1)
    built = rng.uniform(0, 1, sub.shape) < sub          # each 20 m pixel built with the cell's probability
    score = np.where(built, 0.1, -1.0) + rng.normal(0, 0.05, sub.shape)
    comp = satellite.Composite(year=2019, window=w, score=score.astype("float32"), water=np.zeros(sub.shape, bool))
    calib = satellite.calibrate([comp], [ref])
    frac, _water = satellite.cell_fraction(comp, calib["threshold"])
    assert abs(frac.sum() - ref.sum()) / ref.sum() < 0.15
    assert calib["correlation"] > 0.9 and calib["concordance"] > 0.9
    assert satellite.grade({**calib, "cells_compared": 500})["level"] == "bonne"
    assert satellite.grade({**calib, "cells_compared": 150})["level"] == "moyenne"  # too few cells to rate it "bonne"
    assert satellite.grade({**calib, "cells_compared": 50})["level"] == "faible"
    assert satellite.grade({"correlation": -0.4, "f1_built": 0.2, "cells_compared": 50})["level"] == "faible"
    # A brighter season (whole scene shifted) gets a threshold moved by the same amount.
    shifted = satellite.Composite(year=2020, window=w, score=(score + 0.3).astype("float32"), water=comp.water)
    cores, vegs = satellite.invariant_masks(ref, None)
    t = satellite.harmonised_threshold([shifted], [cores], [vegs], float(np.median(score[cores])), float(np.median(score[vegs])),
                                       calib["threshold"])
    assert t == pytest.approx(calib["threshold"] + 0.3, abs=0.02)


def test_fuse_combines_sources_and_ignores_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    store.ensure_communes()
    commune = store.commune(COMMUNE)
    window = grid.Window.from_bbox((-54.06, 5.46, -54.00, 5.52))
    rows, cols = window.shape
    ref = np.zeros(window.shape)
    ref[15:20, 20:25] = 0.8  # town centre (inside the commune, east of the Maroni)
    monkeypatch.setattr(builtup, "analysis_windows", lambda contour, cfg=None: ([window], {"windows": [list(window.bbox)]}))
    monkeypatch.setattr(builtup.wsf, "settlement_2019", lambda w, cfg=None, quick=False: ref if w == window else np.zeros(w.shape))
    monkeypatch.setattr(builtup.wsf, "evolution", lambda w, cfg=None: {y: ref * (0.5 if y < 2000 else 1.0) for y in builtup.wsf.EVOLUTION_YEARS})
    monkeypatch.setattr(builtup.msbuildings, "cells_in", lambda bbox, cfg=None: {})
    rng = np.random.default_rng(2)

    def fake_series(windows: Any, years: Any, refs: Any, reference_year: int, cfg: Any, progress: Any = None, stable: Any = None,
                    focus: Any = None) -> Any:
        out = {}
        for y in years:
            noise = rng.normal(0, 0.01, window.shape)        # forest flicker, below the noise floor
            frac = np.clip(ref + noise, 0, 1)
            if y >= 2022:
                frac[22:25, 24:27] = 0.7                      # new district at the edge of town, real growth
                frac[2:5, 2:5] = 0.9                          # bare soil far from any settlement: ignored
            out[y] = [frac]
        return {"years": out, "water": [np.zeros(window.shape)], "calibration": {"correlation": 0.8, "f1_built": 0.8,
                "cells_compared": 400, "concordance": 0.95, "threshold": -0.2}, "scenes": {}, "errors": {}}

    monkeypatch.setattr(satellite, "series", fake_series)
    meta = builtup.fuse(COMMUNE, commune["contour"], last_year=2025)
    totals = meta["totals_ha"]
    assert totals["2019"] == pytest.approx(25 * 0.8 * grid.CELL_HA, rel=0.02)
    assert totals["1985"] < totals["2015"] <= totals["2016"]            # history joined on 2016
    assert totals["2025"] - totals["2021"] == pytest.approx(9 * 0.7 * grid.CELL_HA, rel=0.1)  # only the real district
    assert meta["sentinel2_applied"] and meta["quality"]["level"] == "bonne"
    data = builtup.load(COMMUNE)
    growth = builtup.growth(data, 2019, 2025)
    assert len([v for v in growth.values() if v > 0.5]) == 9


def test_population_is_calibrated_on_insee_and_extrapolated() -> None:
    seed_commune()
    m2023 = population.model(COMMUNE, 2023)
    assert m2023["total"] == pytest.approx(54429, rel=0.01) and not m2023["extrapolated"]
    m2025 = population.model(COMMUNE, 2025)
    assert m2025["total"] > m2023["total"] and m2025["extrapolated"]
    assert m2025["children_3_10"] == pytest.approx(m2025["total"] * (0.75 * 4000 + 6000) / 50000, rel=0.02)
    store.set_hypothesis(COMMUNE, {"year": 2025, "value": 75000, "source": "mairie"}, "chef")
    hyp = population.model(COMMUNE, 2025, use_hypothesis=True)
    assert hyp["total"] == pytest.approx(75000, rel=0.01) and "mairie" in hyp["calibration"]["basis"]


def test_siting_targets_the_unserved_district() -> None:
    cells = seed_commune()
    acc = access.accessibility(COMMUNE, "ecole", 2025)
    district_cell = cells["district"][0]
    assert acc["cells"][district_cell]["distance_m"] > 1500 and acc["stats"]["coverage_rate"] < 1
    result = access.site(COMMUNE, "ecole", k=1, year=2025)
    site = result["sites"][0]
    assert grid.haversine_m(site["lon"], site["lat"], GROWTH[1], GROWTH[0]) < 1500  # the district is within its radius
    assert result["after"]["coverage_rate"] > result["before"]["coverage_rate"]
    assert result["classes"]["per_site"][0] >= 1 and "enfants" in site["why"]
    assert any(c["label"].startswith("Foncier") and c["status"] == "non vérifié" for c in site["checks"])
    evaluation = access.evaluate(COMMUNE, "ecole", [{"lat": site["lat"], "lon": site["lon"], "name": "École 2027"}], year=2025)
    assert evaluation["gain"]["demand"] > 0


def test_watch_and_census_scout_respect_secrecy(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_commune()
    hot = watch.hotspots(COMMUNE, notify=False, since=2019, until=2025)
    assert hot["summary"]["clusters"] == 1 and hot["clusters"][0]["far_from_school"]
    scout = watch.census_scout(COMMUNE, 2019, until=2025)
    assert scout["rows"] and all(r["new_buildings_est"] >= 5 for r in scout["rows"]) and scout["cell_size_m"] == 200
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "privacy_min_buildings", 10_000)
    hidden = watch.census_scout(COMMUNE, 2019, until=2025)
    assert hidden["rows"] == [] and hidden["hidden"]["cells"] == 16
