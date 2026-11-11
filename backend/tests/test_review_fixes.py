"""Fixes of the project review: secrecy of displayed layers, sync robustness, lost jobs, facility
corrections, school capacity, trip radius, IRIS calibration, frozen scenarios, validation, snapshot."""

from __future__ import annotations

import datetime
import gzip
import json
from typing import Any

import httpx
import pytest

from app.analyse import access, grid, jobs, layers as layer_store, population, privacy
from app.config import get_settings
from app.db import db
from app.territoire import store, sync
from tests.test_analysis import COMMUNE, CORE, GROWTH, seed_commune


def _square(center: Any, half: float) -> dict:
    lat, lon = center
    return {"type": "Polygon", "coordinates": [[[lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half],
                                                [lon - half, lat + half], [lon - half, lat - half]]]}


def test_sparse_cells_are_generalised_in_every_displayed_layer(client_as: Any) -> None:
    cells = seed_commune()
    lone = grid.cell_id(*grid.cell_of(-53.95, 5.42))  # one isolated dwelling far from town
    layer_store.save(COMMUNE, "buildings", {lone: [1, 90.0], cells["core"][0]: [40, 6000.0]}, {}, None)
    data = layer_store.load(COMMUNE, "builtup")[0]
    data["cells"][lone] = [0.0] * 7 + [0.02] * 10
    layer_store.save(COMMUNE, "builtup", data, layer_store.load(COMMUNE, "builtup")[1])
    viewer = client_as("viewer")

    def values(layer: str) -> dict:
        body = viewer.get(f"/api/v1/grille/{COMMUNE}/couche", params={"layer": layer, "year": 2025}).json()
        return {f"{c[0]}_{c[1]}": c[2] for c in body["cells"]}

    assert values("batiments")[lone] == privacy.BELOW and values("batiments")[cells["core"][0]] == 40
    assert values("population")[lone] == privacy.BELOW and values("population")[cells["core"][0]] % 5 == 0
    assert values("bati")[lone] == 0.05  # rounded to 5 %
    dossier = viewer.get(f"/api/v1/grille/{COMMUNE}/carreau/{lone}").json()
    assert dossier["sparse"] and "population" not in dossier and dossier["buildings"]["count"] == privacy.BELOW
    growth = values("croissance")
    assert lone not in growth and all(abs(v) >= privacy.min_growth_ha({"buildings_per_built_ha": 25.0}) for v in growth.values())


def test_partial_overpass_answer_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.sources import osm

    partial = {"elements": [{"type": "node", "id": 1, "lat": 5.5, "lon": -54.0, "tags": {"amenity": "pharmacy"}}],
               "remark": "runtime error: Query timed out in \"query\" at line 1 after 181 seconds."}
    monkeypatch.setattr(osm.httpx, "post", lambda *a, **k: httpx.Response(200, json=partial, request=httpx.Request("POST", "http://x")))
    with pytest.raises(osm.OverpassError):
        osm.facilities(live=True)


def test_mass_deletion_by_a_sync_is_held_back() -> None:
    store.ensure_communes()
    items = [{"uid": f"osm:node/{i}", "category": "eau", "lat": 5.49, "lon": -54.02, "commune": COMMUNE} for i in range(40)]
    store.upsert_equipments(items, "openstreetmap")
    result = store.upsert_equipments(items[:5], "openstreetmap")  # suspicious answer: 35 of 40 missing
    assert result["deletion_held"] == 35 and len(store.equipments(COMMUNE)) == 40
    assert store.upsert_equipments(items[:38], "openstreetmap")["deleted"] == 2  # normal churn still applies


def test_lost_jobs_are_expired_so_the_commune_can_be_analysed_again() -> None:
    store.ensure_communes()
    job = jobs.create("commune", COMMUNE, {}, "t")
    with db() as conn:
        conn.execute("UPDATE analysis_jobs SET status = 'running', started_at = ? WHERE id = ?",
                     ((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=6)).isoformat(), job["id"]))
    again = jobs.create("commune", COMMUNE, {}, "t")
    assert again["created"] and again["id"] != job["id"] and jobs.get(job["id"])["status"] == "failed"
    assert jobs.expire_stale(interrupted=True) == 1  # restart of an inline process: the queued job died with it


def test_corrections_of_open_data_facilities_survive_a_sync() -> None:
    seed_commune()
    school = store.upsert_equipments([{"uid": "uai:IMPRECIS", "category": "ecole", "name": "École du bourg", "commune": COMMUNE,
                                       "lat": CORE[0], "lon": CORE[1], "attributes": {"precision": "Ville", "classes": 4}}],
                                     "education_nationale", replace_source=False)
    item = next(e for e in store.equipments(COMMUNE) if e["uid"] == "uai:IMPRECIS")
    assert item["imprecise"] and school["upserted"] == 1
    store.save_manual_equipment({"category": "ecole", "lat": GROWTH[0], "lon": GROWTH[1], "status": "existant", "note": "relevé terrain"},
                                "chef", item["id"])
    store.upsert_equipments([{"uid": "uai:IMPRECIS", "category": "ecole", "name": "École du bourg", "commune": COMMUNE,
                              "lat": CORE[0], "lon": CORE[1], "attributes": {"precision": "Ville", "classes": 4}}],
                            "education_nationale", replace_source=False)  # next synchronisation
    fixed = store.get_equipment(item["id"])
    assert (fixed["lat"], fixed["lon"]) == GROWTH and not fixed["imprecise"] and fixed["correction"]["fields"] == ["position"]
    assert fixed["attributes"]["classes"] == 4 and fixed["attributes"]["note"] == "relevé terrain"  # source attributes kept


def test_saturated_schools_leave_demand_without_a_place(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_commune()
    school = next(e for e in store.equipments(COMMUNE) if e["uid"] == "uai:TEST")
    with db() as conn:
        conn.execute("UPDATE equipments SET attributes = ? WHERE id = ?", (json.dumps({"classes": 2}), school["id"]))
    acc = access.accessibility(COMMUNE, "ecole", 2025)
    row = next(f for f in acc["facilities"] if f["id"] == school["id"])
    assert row["places"] == 2 * get_settings().school_class_size and row["saturation"] > 1
    assert acc["stats"]["demand_saturated"] > 0 and acc["stats"]["served_rate"] < acc["stats"]["coverage_rate"]
    result = access.site(COMMUNE, "ecole", k=1, year=2025)
    assert result["before"]["coverage_rate"] == acc["stats"]["served_rate"]


def test_coverage_uses_the_estimated_trip_distance(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_commune()
    cfg = get_settings()
    monkeypatch.setattr(cfg, "detour_factor", 1.0)
    straight = access.accessibility(COMMUNE, "ecole", 2025)["stats"]["coverage_rate"]
    monkeypatch.setattr(cfg, "detour_factor", 2.0)
    winding = access.accessibility(COMMUNE, "ecole", 2025)
    assert winding["radius_m"] == winding["radius_trip_m"] / 2 and winding["stats"]["coverage_rate"] <= straight


def test_population_is_calibrated_by_district_when_iris_are_published() -> None:
    cells = seed_commune()
    layer_store.save(COMMUNE, "iris", {"year": 2023, "zones": [
        {"code": "973110102", "nom": "Centre", "geometry": _square((CORE[0] + 0.0045, CORE[1] + 0.0045), 0.006),
         "ages": {"_T": 20000, "Y2T5": 1000, "Y6T10": 1500, "Y11T14": 1000, "Y15T17": 600}},
    ], "unmatched": []}, {})
    m = population.model(COMMUNE, 2023)
    assert m["calibration"]["level"] == "iris" and m["total"] == pytest.approx(54429, rel=0.01)  # commune total preserved
    core_pop = sum(m["cells"][c]["pop"] for c in cells["core"] if c in m["cells"])
    assert core_pop == pytest.approx(20000, rel=0.02)
    kids_share = m["cells"][cells["core"][0]]["enfants_3_10"] / m["cells"][cells["core"][0]]["pop"]
    assert kids_share == pytest.approx((0.75 * 1000 + 1500) / 20000, rel=0.02)  # the district's own age structure


def test_inconsistent_iris_figures_fall_back_to_the_commune() -> None:
    seed_commune()
    layer_store.save(COMMUNE, "iris", {"year": 2023, "zones": [
        {"code": "973110102", "nom": "Centre", "geometry": _square(CORE, 0.006), "ages": {"_T": 90000}},
    ], "unmatched": []}, {})
    assert population.model(COMMUNE, 2023)["calibration"]["level"] == "commune"


def test_protection_levels() -> None:
    from app.sources.protected import _clean, level

    assert level("V", "Parc naturel régional") == "encadrée"
    assert level("V", "Parc national, aire d'adhésion") == "encadrée"
    assert level("Ib", "Réserve biologique intégrale") == "stricte"
    assert level("IV", "Wetland of International Importance (Ramsar Site)") == "encadrée"
    assert _clean("Guyane [Aire D\\\\'Adhésion]") == "Guyane [Aire D'Adhésion]"


def test_visual_validation_sample_and_agreement(client_as: Any) -> None:
    seed_commune()
    analyst = client_as("analyst")
    body = analyst.get(f"/api/v1/validation/{COMMUNE}", params={"year": 2025}).json()
    assert body["cells"] and body["cells"] == analyst.get(f"/api/v1/validation/{COMMUNE}", params={"year": 2025}).json()["cells"]
    assert all("predicted_share" not in c for c in body["cells"])  # blind until voted
    from app.analyse import builtup

    truth = builtup.year_values(builtup.load(COMMUNE), 2025)
    for c in body["cells"][:6]:
        verdict = "bati" if truth.get(c["cell"], 0.0) >= 0.2 else "non_bati"
        answer = analyst.post(f"/api/v1/validation/{COMMUNE}", json={"cell": c["cell"], "year": 2025, "verdict": verdict,
                                                                      "imagery": "EOX 2025"}).json()
        report = answer["report"]
        assert answer["predicted_share"] == round(truth.get(c["cell"], 0.0), 3)
    assert report["decided"] == 6 and report["agreement"] == 1.0 and not report["reached"]  # 50 cells required
    assert client_as("viewer", "elu").post(f"/api/v1/validation/{COMMUNE}", json={"cell": "1_1", "year": 2025, "verdict": "bati"}).status_code == 403


def test_root_certificate_is_downloadable(client_as: Any) -> None:
    response = client_as("viewer").get("/api/v1/rapports/certificat")
    assert response.status_code == 200 and b"BEGIN CERTIFICATE" in response.content
    assert len(response.headers["x-root-fingerprint-sha256"]) == 64


def test_altered_snapshot_is_refused(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    snap = tmp_path / "snapshot_973.json.gz"
    store.ensure_communes()
    sync.export_snapshot(snap)
    monkeypatch.setattr(sync, "SNAPSHOT", snap)
    payload = json.loads(gzip.decompress(snap.read_bytes()))
    payload["indicators"] = [["97311", "population", 2023, 999999, "falsifié", "x"]]
    snap.write_bytes(gzip.compress(json.dumps(payload).encode()))  # tampered, sidecar unchanged
    assert sync.load_snapshot_if_empty() is None
    assert store.series("97311", ("population",)).get("population") is None
