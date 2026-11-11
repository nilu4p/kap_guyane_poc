"""Fixes of the security / stability / performance review specific to the territorial platform: blind
validation, atomic job creation, bounded memory. The shared security core (proxies, lockout, session
probe, custom-source secrets, DNS rebinding, imagery tiles, audit) is tested in test_shared_core.py."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List

import numpy as np
import pytest

from app.analyse import grid, jobs, watch
from app.config import get_settings
from tests.test_analysis import COMMUNE, seed_commune


def test_blind_validation_hides_the_answer_revealed_by_other_controllers(client_as: Callable[[str], Any]) -> None:
    seed_commune()
    first, second = client_as("analyst", "controller-a"), client_as("analyst", "controller-b")
    sample = first.get(f"/api/v1/validation/{COMMUNE}").json()
    cell, year = sample["cells"][0]["cell"], sample["year"]
    voted = first.post(f"/api/v1/validation/{COMMUNE}", json={"cell": cell, "year": year, "verdict": "bati"}).json()
    assert "predicted" in voted["report"]["entries"][0]  # revealed to the person who voted
    other = second.get(f"/api/v1/validation/{COMMUNE}").json()
    assert other["report"]["checked"] == 1 and "predicted" not in other["report"]["entries"][0]
    assert all("predicted_share" not in c for c in other["cells"])


def test_verdict_for_a_year_outside_the_series_is_reported_on_the_stored_year(client_as: Callable[[str], Any]) -> None:
    seed_commune()
    analyst = client_as("analyst")
    cell = analyst.get(f"/api/v1/validation/{COMMUNE}").json()["cells"][0]["cell"]
    answer = analyst.post(f"/api/v1/validation/{COMMUNE}", json={"cell": cell, "year": 2003, "verdict": "non_bati"})
    assert answer.status_code == 200 and answer.json()["report"]["checked"] == 1  # stored for 2005, reported for 2005
    too_long = analyst.post(f"/api/v1/validation/{COMMUNE}", json={"cell": cell, "year": 2025, "verdict": "bati", "imagery": "x" * 81})
    assert too_long.status_code == 422


def test_cell_dossier_coverage_uses_the_estimated_trip(client_as: Callable[[str], Any], monkeypatch: pytest.MonkeyPatch) -> None:
    cells = seed_commune()
    cfg = get_settings()
    monkeypatch.setattr(cfg, "detour_factor", 2.0)
    monkeypatch.setattr(cfg, "coverage_radii_m", {**cfg.coverage_radii_m, "ecole": 1000})
    dossier = client_as("viewer").get(f"/api/v1/grille/{COMMUNE}/carreau/{cells['core'][0]}").json()
    school = dossier["nearest"]["ecole"]
    assert school["walk_m"] == pytest.approx(school["distance_m"] * 2.0, abs=1)
    assert school["covered"] == (school["walk_m"] <= 1000)


def test_a_pending_job_is_never_created_twice() -> None:
    seed_commune()
    first = jobs.create("commune", COMMUNE, {}, "a")
    second = jobs.create("commune", COMMUNE, {}, "b")
    assert first["created"] and not second["created"] and second["id"] == first["id"]


def test_progress_writes_are_throttled(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: List[Dict[str, Any]] = []
    monkeypatch.setattr(jobs, "_update", lambda job_id, settings, **fields: writes.append(fields))
    progress = jobs.Progress(1, None)
    for pct in range(50):
        progress("Série Sentinel-2", pct)
    progress("Fusion", 60)
    progress("Fusion", 100)
    assert len(writes) == 3 and writes[-1]["progress"] == 100


def test_nearest_bounds_memory_and_matches_brute_force(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(1)
    pts = rng.uniform([-54.1, 5.3], [-53.9, 5.6], size=(300, 2))
    targets = rng.uniform([-54.1, 5.3], [-53.9, 5.6], size=(1000, 2))
    monkeypatch.setattr(grid, "MAX_PAIRS_PER_CHUNK", 5000)  # 5 points per chunk
    dist, idx = grid.nearest(pts[:, 0], pts[:, 1], targets[:, 0], targets[:, 1])
    full = grid.haversine_m(pts[:, 0][:, None], pts[:, 1][:, None], targets[:, 0][None, :], targets[:, 1][None, :])
    assert np.array_equal(idx, full.argmin(axis=1)) and np.allclose(dist, full.min(axis=1))


def test_census_list_is_deterministic_and_reports_current_share() -> None:
    seed_commune()
    first = watch.census_scout(COMMUNE, 2019)
    assert first["rows"] and first == watch.census_scout(COMMUNE, 2019)
    gains = [r["growth_ha"] for r in first["rows"]]
    assert gains == sorted(gains, reverse=True)
    assert all(0 < r["built_share_now"] <= 1 for r in first["rows"])


def test_supervision_folder_sizes_are_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    from app.services import supervision

    calls: List[Any] = []
    monkeypatch.setattr(supervision, "_dir_size", lambda path, limit_files=0: calls.append(path) or 1)
    monkeypatch.setattr(supervision, "_sizes_cache", {})
    folders = {"cache": tmp_path / "c", "data": tmp_path / "d"}
    supervision._folder_sizes(folders)
    supervision._folder_sizes(folders)
    assert len(calls) == 2  # measured once for the two folders, then served from the cache
    monkeypatch.setattr(supervision, "DISK_SIZES_TTL_S", 0.0)
    time.sleep(0.001)
    supervision._folder_sizes(folders)
    assert len(calls) == 4


def test_siting_without_inhabited_cells_is_explained(client_as: Callable[[str], Any]) -> None:
    from app.analyse import layers as layer_store

    seed_commune()
    data, meta, _ = layer_store.load(COMMUNE, "builtup")
    layer_store.save(COMMUNE, "builtup", {"years": data["years"], "cells": {}}, meta)
    answer = client_as("viewer").post("/api/v1/decision/implantation", json={"commune": COMMUNE, "category": "ecole"})
    assert answer.status_code == 200 and answer.json()["available"] is False
