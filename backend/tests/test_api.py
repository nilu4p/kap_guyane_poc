"""API: territory profiles, facilities, grid layers, decision support, scenarios, signed reports, ethics."""

from __future__ import annotations

from typing import Any

from app.core import audit
from app.db import db
from app.territoire import profile, store
from tests.test_analysis import COMMUNE, GROWTH, seed_commune


def test_profiles_derive_rates_with_comparison_and_rank(client_as: Any) -> None:
    seed_commune()
    viewer = client_as("viewer")
    communes = viewer.get("/api/v1/communes").json()
    assert len(communes["communes"]) == 22 and communes["default"] == "97311"
    assert next(c for c in communes["communes"] if c["code"] == COMMUNE)["analysed_at"]
    body = viewer.get(f"/api/v1/communes/{COMMUNE}").json()
    demo = next(t for t in body["themes"] if t["id"] == "demographie")["kpis"]
    under15 = next(k for k in demo if k["id"] == "part_moins_15")
    assert under15["value"] == 41.5 and under15["guyane"] == 32.0 and under15["rank"] == 1 and under15["sources"]
    growth = next(k for k in demo if k["id"] == "croissance_pop")
    assert growth["value"] == round(((54429 / 42612) ** (1 / 6) - 1) * 100, 2)
    table = viewer.get("/api/v1/territoire/kpis").json()
    assert {k["id"] for k in table["kpis"]} == {k.id for k in profile.KPIS}
    assert viewer.get("/api/v1/communes/99999").status_code == 404


def test_population_hypothesis_is_kept_beside_insee(client_as: Any) -> None:
    seed_commune()
    chef = client_as("supervisor")
    assert chef.put(f"/api/v1/communes/{COMMUNE}/hypothese", json={"year": 2025, "value": 75000, "low": 70000, "high": 80000,
                                                                   "source": "estimation mairie"}).status_code == 200
    body = chef.get(f"/api/v1/communes/{COMMUNE}").json()
    assert body["hypothesis"]["value"] == 75000
    assert next(k for k in body["themes"][0]["kpis"] if k["id"] == "population")["value"] == 54429  # official figure untouched
    assert chef.put(f"/api/v1/communes/{COMMUNE}/hypothese", json={"year": 2025, "value": 1, "low": 9, "high": 2}).status_code == 422
    assert any(e["action"] == "territory.hypothesis" for e in audit.search(limit=20))


def test_facilities_open_data_are_protected_manual_ones_editable(client_as: Any) -> None:
    seed_commune()
    analyst = client_as("analyst")
    created = analyst.post("/api/v1/equipements", json={"category": "eau", "name": "Borne-fontaine Chekepatty", "commune": COMMUNE,
                                                        "lat": GROWTH[0], "lon": GROWTH[1], "status": "projet"}).json()["equipment"]
    assert created["source"] == "saisie" and created["status"] == "projet"
    school = next(e for e in store.equipments(COMMUNE) if e["source"] == "education_nationale")
    edited = analyst.put(f"/api/v1/equipements/{school['id']}", json={"category": "ecole", "lat": 0 + school["lat"], "lon": school["lon"],
                                                                       "capacity": 420, "status": "existant", "note": "extension"}).json()["equipment"]
    assert edited["capacity"] == 420 and edited["name"] == "École du centre"  # open-data identity kept
    assert analyst.delete(f"/api/v1/equipements/{school['id']}").status_code == 409
    assert analyst.delete(f"/api/v1/equipements/{created['id']}").status_code == 200
    assert analyst.post("/api/v1/equipements", json={"category": "eau", "lat": 48.85, "lon": 2.35}).status_code == 422  # not in Guiana


def test_grid_layers_are_compact_and_200_m(client_as: Any) -> None:
    seed_commune()
    viewer = client_as("viewer")
    meta = viewer.get(f"/api/v1/grille/{COMMUNE}/meta").json()
    assert meta["analysed"] and meta["grid"]["cell_m"] == 200 and meta["builtup"]["quality"]["level"] == "bonne"
    for layer in ("bati", "croissance", "population", "enfants", "acces"):
        body = viewer.get(f"/api/v1/grille/{COMMUNE}/couche", params={"layer": layer, "year": 2025}).json()
        assert body["available"] and body["cells"] and all(isinstance(c[0], int) and isinstance(c[1], int) for c in body["cells"])
    access = viewer.get(f"/api/v1/grille/{COMMUNE}/couche", params={"layer": "acces", "category": "ecole"}).json()
    assert access["stats"]["coverage_rate"] < 1 and access["radius_trip_m"] == 1500 and access["radius_m"] == 1500 / 1.3
    cell = f"{access['cells'][0][0]}_{access['cells'][0][1]}"
    dossier = viewer.get(f"/api/v1/grille/{COMMUNE}/carreau/{cell}").json()
    assert dossier["cell_m"] == 200 and dossier["built_series"] and dossier["nearest"]["ecole"]
    assert viewer.get(f"/api/v1/grille/{COMMUNE}/couche", params={"layer": "parcelles"}).status_code == 422


def test_census_export_is_aggregated_audited_and_reserved(client_as: Any) -> None:
    seed_commune()
    assert client_as("viewer", "elu").get(f"/api/v1/grille/{COMMUNE}/recensement").status_code == 403
    analyst = client_as("analyst")
    response = analyst.get(f"/api/v1/grille/{COMMUNE}/recensement", params={"format": "csv"})
    assert response.status_code == 200 and "carreau_200m" in response.text and "Aucune construction individuelle" in response.text
    assert any(e["action"] == "export.census" for e in audit.search(limit=20))


def test_decision_scenario_and_signed_report_flow(client_as: Any) -> None:
    seed_commune()
    analyst = client_as("analyst")
    proposal = analyst.post("/api/v1/decision/implantation", json={"commune": COMMUNE, "category": "ecole", "k": 1, "year": 2025}).json()
    assert proposal["available"] and len(proposal["sites"]) == 1
    sites = [{"lat": s["lat"], "lon": s["lon"], "name": f"Site {s['rank']}"} for s in proposal["sites"]]
    scenario = analyst.post("/api/v1/scenarios", json={"commune_code": COMMUNE, "category": "ecole", "name": "École provisoire 2027",
                                                       "sites": sites}).json()["scenario"]
    assert scenario["evaluation"]["gain"]["demand"] > 0 and scenario["status"] == "brouillon"
    draft = analyst.post("/api/v1/rapports/projet", json={"kind": "implantation", "scenario_id": scenario["id"]}).json()
    assert draft["draft"] and "Charte d'usage".upper() in draft["content"]
    assert analyst.post("/api/v1/rapports/emettre", json={"kind": "implantation", "scenario_id": scenario["id"]}).status_code == 403
    chef = client_as("supervisor")
    assert chef.post(f"/api/v1/scenarios/{scenario['id']}/statut", json={"status": "valide"}).json()["scenario"]["status"] == "valide"
    assert analyst.put(f"/api/v1/scenarios/{scenario['id']}", json={"commune_code": COMMUNE, "category": "ecole", "name": "x",
                                                                    "sites": sites}).status_code == 409  # validated = frozen
    report = chef.post("/api/v1/rapports/emettre", json={"kind": "implantation", "scenario_id": scenario["id"],
                                                         "addressees": "Maire, DGS"}).json()
    assert report["ref"].startswith("IMPL-") and report["signed"]
    check = chef.post(f"/api/v1/rapports/{report['id']}/verifier").json()
    assert check["valid"] and check["signature_ok"] and check["chain_ok"]
    with db() as conn:
        conn.execute("UPDATE reports SET content = replace(content, 'Maire', 'Préfet') WHERE id = ?", (report["id"],))
    assert chef.post(f"/api/v1/rapports/{report['id']}/verifier").json()["valid"] is False
    exported = chef.get(f"/api/v1/rapports/{report['id']}/export")
    assert exported.status_code == 200 and "SCELLEMENT KAP Guyane" in exported.text


def test_diagnostic_and_census_documents(client_as: Any) -> None:
    seed_commune()
    chef = client_as("supervisor")
    diag = chef.post("/api/v1/rapports/emettre", json={"kind": "diagnostic", "commune": COMMUNE}).json()
    assert diag["ref"].startswith("DIAG-") and "pas un contre-recensement" in " ".join(diag["content"].split())
    ril = chef.post("/api/v1/rapports/emettre", json={"kind": "recensement", "commune": COMMUNE, "since": 2019}).json()
    assert ril["ref"].startswith("RIL-") and "200 m" in ril["content"]
    assert len(chef.get("/api/v1/rapports").json()["reports"]) == 2


def test_ethics_charter_and_catalogue(client_as: Any) -> None:
    viewer = client_as("viewer")
    charter = viewer.get("/api/v1/system/ethique").json()
    assert any("200 m" in p["title"] for p in charter["principles"])
    catalogue = viewer.get("/api/v1/system/catalogue").json()["sources"]
    statuses = {s["id"]: s["status"] for s in catalogue}
    assert statuses["majic"] == "exclue" and statuses["insee_melodi"] == "intégrée"


def test_validated_scenario_figures_are_frozen_in_the_signed_file(client_as: Any) -> None:
    seed_commune()
    chef = client_as("supervisor")
    sites = [{"lat": GROWTH[0], "lon": GROWTH[1], "name": "École 2027"}]
    scenario = chef.post("/api/v1/scenarios", json={"commune_code": COMMUNE, "category": "ecole", "name": "S", "sites": sites}).json()["scenario"]
    validated = chef.post(f"/api/v1/scenarios/{scenario['id']}/statut", json={"status": "valide"}).json()["scenario"]
    frozen_gain = validated["evaluation"]["gain"]["demand"]
    assert validated["evaluation"]["frozen_at"] and frozen_gain > 0
    # Data change after validation: a new school is entered next to the planned site.
    store.save_manual_equipment({"category": "ecole", "lat": GROWTH[0], "lon": GROWTH[1], "status": "existant", "name": "Autre"}, "t")
    report = chef.post("/api/v1/rapports/emettre", json={"kind": "implantation", "scenario_id": scenario["id"]}).json()
    text = " ".join(report["content"].split())
    assert "Chiffres figés à la validation" in text and f"+{frozen_gain:,}".replace(",", " ") in text
