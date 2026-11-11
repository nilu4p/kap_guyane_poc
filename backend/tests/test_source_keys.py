"""API keys of the data sources: vault, live checks and keyed fallbacks (Copernicus, Protected Planet)."""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict

import httpx
import pytest

from app.config import get_settings
from app.core import credentials, vault
from app.sources import cdse, health, protected, sentinel2

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
CDSE_ITEM = {
    "id": "S2B_MSIL2A_20240915T140709_N0511_R110_T21NZF_20240915T175614.SAFE",
    "bbox": [-54.1, 5.4, -53.9, 5.6],
    "geometry": {"type": "Polygon", "coordinates": [[[-54.1, 5.4], [-53.9, 5.4], [-53.9, 5.6], [-54.1, 5.4]]]},
    "properties": {"datetime": "2024-09-15T14:07:09Z", "eo:cloud_cover": 12.3},
}


@pytest.fixture(autouse=True)
def _fresh_token() -> None:
    cdse._token.clear()


def _response(status: int = 200, payload: Any = None, content: bytes = b"") -> httpx.Response:
    request = httpx.Request("POST", "https://example.org")
    if payload is not None:
        return httpx.Response(status, json=payload, request=request)
    return httpx.Response(status, content=content, request=request)


def fake_cdse(monkeypatch: pytest.MonkeyPatch, calls: list) -> None:
    def post(url: str, **kwargs: Any) -> httpx.Response:
        calls.append(url)
        if url.endswith("/token"):
            assert kwargs["data"]["grant_type"] == "client_credentials"
            return _response(payload={"access_token": "TOKEN", "expires_in": 600})
        assert kwargs["headers"]["Authorization"] == "Bearer TOKEN"
        if url.endswith("/catalog/1.0.0/search"):
            return _response(payload={"features": [CDSE_ITEM]})
        if url.endswith("/process"):
            assert kwargs["json"]["input"]["data"][0]["dataFilter"]["timeRange"]["from"] == "2024-09-15T00:00:00Z"
            return _response(content=PNG)
        raise AssertionError(url)

    monkeypatch.setattr(cdse.httpx, "post", post)


def configure_cdse(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = get_settings()
    monkeypatch.setattr(cfg, "cdse_client_id", "client-id")
    monkeypatch.setattr(cfg, "cdse_client_secret", "client-secret-XYZ1")


def test_source_keys_saved_encrypted_and_write_only(client_as: Any) -> None:
    admin = client_as("admin")
    body = {"cdse_client_id": "sh-0123456789", "cdse_client_secret": "SECRET-abcdefgh-1234", "protected_planet_token": "pp-token-98765432"}
    response = admin.put("/api/v1/settings/keys", json=body)
    assert response.status_code == 200
    for value in body.values():
        assert value not in response.text
    keys = response.json()["keys"]
    assert keys["cdse_client_secret"] == {**keys["cdse_client_secret"], "configured": True, "origin": "dashboard",
                                          "kind": "source", "service": "copernicus_cdse", "hint": "••••1234"}
    assert keys["alert_webhook_url"]["kind"] == "notification"
    raw = (get_settings().keys_dir / credentials.STORE_NAME).read_bytes()
    assert b"SECRET-abcdefgh" not in raw and json.loads(vault.decrypt(raw))["protected_planet_token"] == body["protected_planet_token"]
    cfg = get_settings()
    assert (cfg.cdse_client_id, cfg.cdse_client_secret, cfg.protected_planet_token) == tuple(body.values())  # applied live
    catalogue = {s["id"]: s for s in admin.get("/api/v1/system/catalogue").json()["sources"]}
    assert catalogue["copernicus_cdse"]["status"] == catalogue["protected_planet"]["status"] == "intégrée"
    # removal restores the (empty) .env value
    keys = admin.put("/api/v1/settings/keys", json={"protected_planet_token": ""}).json()["keys"]
    assert not keys["protected_planet_token"]["configured"] and get_settings().protected_planet_token == ""
    catalogue = {s["id"]: s for s in admin.get("/api/v1/system/catalogue").json()["sources"]}
    assert catalogue["protected_planet"]["status"] == "clé requise"


def test_source_keys_admin_only_and_validated(client_as: Any) -> None:
    assert client_as("supervisor").put("/api/v1/settings/keys", json={"cdse_client_id": "x"}).status_code == 403
    admin = client_as("admin")
    assert admin.put("/api/v1/settings/keys", json={"cdse_client_id": "with space"}).status_code == 422
    assert admin.put("/api/v1/settings/keys", json={"unknown_key": "x"}).status_code == 400  # extra fields ignored → nothing to change


def test_key_check_unconfigured_then_valid(client_as: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    admin = client_as("admin")
    result = admin.post("/api/v1/settings/keys/test/copernicus_cdse").json()
    assert not result["ok"] and "non configurés" in result["message"]
    configure_cdse(monkeypatch)
    fake_cdse(monkeypatch, [])
    result = admin.post("/api/v1/settings/keys/test/copernicus_cdse").json()
    assert result["ok"] and "1 scènes" in result["message"]


def test_cdse_refused_credentials_never_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_cdse(monkeypatch)
    monkeypatch.setattr(cdse.httpx, "post", lambda url, **k: _response(401, payload={"error": "invalid_client"}))
    with pytest.raises(cdse.CdseError, match="refusés") as exc:
        cdse.check()
    assert "client-secret" not in str(exc.value)


def test_earth_search_identifier() -> None:
    assert cdse.earth_search_id(CDSE_ITEM["id"]) == "S2B_21NZF_20240915_0_L2A"
    assert sentinel2.ITEM_ID.match(cdse.earth_search_id(CDSE_ITEM["id"]))
    assert cdse.earth_search_id("S1A_IW_GRDH_1SDV_20240915") is None


def test_scenes_fall_back_to_copernicus(monkeypatch: pytest.MonkeyPatch) -> None:
    at = datetime.datetime(2024, 9, 20, tzinfo=datetime.timezone.utc)
    assert sentinel2.scenes(at=at)["available"] is False  # Earth Search offline, no key
    configure_cdse(monkeypatch)
    calls: list = []
    fake_cdse(monkeypatch, calls)
    monkeypatch.setattr(sentinel2, "_post", lambda *a, **k: None)
    payload = sentinel2.scenes(at=at, days=20)
    assert payload["available"] and "Copernicus Data Space" in payload["source"]
    assert [f["properties"]["item_id"] for f in payload["features"]] == ["S2B_21NZF_20240915_0_L2A"]
    assert payload["features"][0]["properties"]["tile"] == "21NZF"


def test_tile_falls_back_to_copernicus(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_a: Any) -> bytes:
        raise sentinel2.Sentinel2Error("catalogue injoignable")

    monkeypatch.setattr(sentinel2, "_render_earth_search", broken)
    x, y = sentinel2.lonlat_to_tile(-54.0, 5.5, 12)
    with pytest.raises(sentinel2.Sentinel2Error):
        sentinel2.render_tile("S2B_21NZF_20240915_0_L2A", 12, x, y)  # no key: the error is kept
    configure_cdse(monkeypatch)
    calls: list = []
    fake_cdse(monkeypatch, calls)
    assert sentinel2.render_tile("S2B_21NZF_20240915_0_L2A", 12, x, y) == PNG
    assert sentinel2.render_tile("S2B_21NZF_20240915_0_L2A", 12, x, y) == PNG  # disk cache
    assert sum(url.endswith("/process") for url in calls) == 1 and sum(url.endswith("/token") for url in calls) == 1


def test_protected_areas_fall_back_to_protected_planet(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "pp-SECRET-token-1"
    monkeypatch.setattr(get_settings(), "protected_planet_token", token)
    seen: Dict[str, Any] = {}

    def get(url: str, **kwargs: Any) -> httpx.Response:
        seen.update(url=url, params=kwargs["params"])
        return _response(payload={"protected_areas": [
            {"wdpa_id": 1, "name": "Réserve naturelle de l'Amana", "designation": {"name": "Réserve naturelle nationale"},
             "iucn_category": {"name": "IV"}, "legal_status_updated_at": "1998-03-13",
             "geojson": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-53.9, 5.6], [-53.7, 5.6], [-53.7, 5.8], [-53.9, 5.6]]]}}},
            {"wdpa_id": 2, "name": "Loin", "designation": {"name": "Site"}, "iucn_category": {"name": "V"},
             "geojson": {"type": "Polygon", "coordinates": [[[-52.0, 3.0], [-51.9, 3.0], [-51.9, 3.1], [-52.0, 3.0]]]}},
        ]})

    monkeypatch.setattr(protected.httpx, "get", get)
    areas = protected.areas((-54.0, 5.4, -53.5, 5.9))
    assert [a["properties"] for a in areas] == [{"name": "Réserve naturelle de l'Amana", "designation": "Réserve naturelle nationale",
                                                "iucn": "IV", "status_year": 1998, "level": "stricte"}]
    assert seen["params"]["country"] == "GUF" and seen["params"]["token"] == token and token not in seen["url"]
    assert health.snapshot()["protected_planet"]["status"] == "ok"
    assert "jeton valide · 2 aires" in protected.check()


def test_protected_planet_refused_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "protected_planet_token", "bad-token-123")
    monkeypatch.setattr(protected.httpx, "get", lambda url, **k: _response(401, payload={"error": "unauthorized"}))
    assert protected.areas((-54.0, 5.4, -53.5, 5.9)) == []  # no stale cache: empty, never an exception
    with pytest.raises(protected.ProtectedPlanetError, match="jeton refusé"):
        protected.check()
