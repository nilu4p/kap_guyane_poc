"""The 200 m grid and the parsing of the open-data sources (offline)."""

from __future__ import annotations

import gzip
import io
import json
import math

import numpy as np
import pytest

from app.analyse import grid
from app.sources import education, melodi, msbuildings, osm, wsf


def test_cells_are_200_m_and_ids_round_trip() -> None:
    row, col = grid.cell_of(-54.03, 5.50)
    west, south, east, north = grid.cell_bounds(row, col)
    assert west <= -54.03 < east and south <= 5.50 < north
    width = grid.haversine_m(west, 5.5, east, 5.5)
    height = grid.haversine_m(-54.03, south, -54.03, north)
    assert abs(width - 200) < 2 and abs(height - 200) < 2  # < 1 % everywhere in Guiana
    assert grid.parse_cell(grid.cell_id(row, col)) == (row, col)


def test_window_indexing_and_sparse_round_trip() -> None:
    w = grid.Window.from_bbox((-54.05, 5.45, -54.00, 5.50))
    rows, cols = w.shape
    assert w.index(*w.cell_at(0, 0)) == (0, 0) and w.cell_at(0, 0)[0] == w.row1  # i = 0 is the northern edge
    lon, lat = w.centers()
    assert lat[0, 0] > lat[-1, 0] and lon[0, -1] > lon[0, 0]
    array = np.zeros(w.shape)
    array[2, 3] = 0.5
    sparse = w.to_sparse(array)
    assert list(sparse.values()) == [0.5] and np.array_equal(w.from_sparse(sparse), array)


def test_mask_inside_and_nearest() -> None:
    w = grid.Window.from_bbox((-54.10, 5.40, -54.00, 5.50))
    square = {"type": "Polygon", "coordinates": [[[-54.08, 5.42], [-54.02, 5.42], [-54.02, 5.48], [-54.08, 5.48], [-54.08, 5.42]]]}
    mask = grid.mask_inside(w, square)
    assert 0 < mask.mean() < 1
    d, idx = grid.nearest(np.array([-54.05]), np.array([5.45]), np.array([-54.0, -54.05]), np.array([5.45, 5.46]))
    assert idx[0] == 1 and abs(d[0] - 1112) < 2


def test_melodi_helpers() -> None:
    obs = [
        {"dimensions": {"GEO": "2026-COM-97311", "TIME_PERIOD": "2023", "AGE": "_T"}, "measures": {"OBS_VALUE_NIVEAU": {"value": 54429.0}}},
        {"dimensions": {"GEO": "2025-DEP-973", "TIME_PERIOD": "2023", "AGE": "_T"}, "measures": {"OBS_VALUE_NIVEAU": {"value": 293996.0}}},
        {"dimensions": {"GEO": "2026-COM-97311", "TIME_PERIOD": "2023", "AGE": "Y_LT15"}, "measures": {"OBS_VALUE_NIVEAU": {"value": 22000.0}}},
    ]
    assert melodi.geo_code("2026-COM-97311") == "97311" and melodi.geo_code("2025-DEP-973") == "973"
    totals = melodi.by_geo_year(melodi.select(obs, AGE="_T"))
    assert totals == {"97311": {2023: 54429.0}, "973": {2023: 293996.0}}
    assert melodi.geo_params(["97311"], "973") == ["COM-97311", "DEP-973"]


def test_enrolment_commune_resolution_uses_directory_then_postal_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(education, "schools", lambda cfg, live: [{"uai": "9730043J", "commune": "97311"}])
    resolve = education.commune_resolver(live=False)
    assert resolve("9730043J", "97320") == "97311"      # directory wins
    assert resolve("UNKNOWN", "97320") == "97311"       # postal code of Saint-Laurent
    assert resolve("UNKNOWN", "97302") == "97302"       # already an INSEE code


def test_osm_classification() -> None:
    assert osm.classify({"amenity": "pharmacy"}) == ("sante", "pharmacy")
    assert osm.classify({"man_made": "water_tap"}) == ("eau", "water_tap")
    assert osm.classify({"shop": "convenience"}) == ("alimentation", "convenience")
    assert osm.classify({"highway": "bus_stop"}) == ("transport", "bus_stop")
    assert osm.classify({"amenity": "townhall"}) == ("services", "townhall")
    assert osm.classify({"building": "yes"}) is None


def test_footprints_are_reduced_to_cell_counts(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    assert msbuildings.quadkey(0, 0, 1) == "0" and msbuildings.quadkey(1, 1, 1) == "3"
    assert "032332011" in msbuildings.quadkeys((-54.05, 5.45, -54.0, 5.5))
    # 20 m × 10 m building near Saint-Laurent.
    ring = [[-54.03, 5.50], [-54.03 + 20 / 111_000, 5.50], [-54.03 + 20 / 111_000, 5.50 + 10 / 110_574], [-54.03, 5.50 + 10 / 110_574], [-54.03, 5.50]]
    area, lon, lat = msbuildings._ring_area_m2(ring)
    assert abs(area - 200) < 5
    line = json.dumps({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}})
    body = gzip.compress((line + "\n" + line + "\n").encode())

    class Response:
        content = body

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(msbuildings.httpx, "get", lambda *a, **k: Response())
    cells = msbuildings._aggregate("https://minedbuildings.z5.web.core.windows.net/global-buildings/x.csv.gz", __import__("app.config").config.get_settings())
    (cid, (count, total)), = cells.items()
    assert cid == grid.cell_id(*grid.cell_of(lon, lat)) and count == 2 and abs(total - 400) < 10


def test_wsf_tiles_cover_the_window() -> None:
    assert wsf.tiles((-54.1, 5.3, -53.9, 5.6)) == [(-56, 4), (-54, 4)]  # Saint-Laurent straddles two 2° tiles
    cfg = __import__("app.config").config.get_settings()
    assert wsf.tile_url("wsf2019", -54, 4, cfg).endswith("/WSF2019_v1_-54_4.tif")
    assert wsf.tile_url("evolution", -56, 4, cfg).endswith("/WSFevolution_v1_-56_4.tif")
