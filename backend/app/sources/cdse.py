"""Copernicus Data Space Ecosystem (Sentinel Hub) — keyed fallback of the Sentinel-2 imagery.

Used only when an OAuth client (``CDSE_CLIENT_ID`` / ``CDSE_CLIENT_SECRET``, editable in
Administration › Paramètres) is configured and Earth Search (AWS open data) fails:

- ``search``: Sentinel Hub Catalog (STAC) items, renamed to the Earth Search identifier
  scheme (``S2A_21NZF_20240915_0_L2A``) so the rest of the platform is unchanged;
- ``render_tile``: one 256 px true-colour PNG through the Process API, for the
  acquisition day of a scene (the free CDSE tier has a monthly quota: fallback only).

The client secret and the access token are never logged nor stored outside the vault.
"""

from __future__ import annotations

import datetime
import re
import threading
import time
from typing import Any, Dict, List, Optional, Sequence

import httpx

from app.config import Settings, get_settings
from app.sources import health
from app.sources.http import USER_AGENT

SOURCE = "copernicus_cdse"
COLLECTION = "sentinel-2-l2a"
# S2A_MSIL2A_20240915T140711_N0511_R110_T21NZF_20240915T175614(.SAFE)
PRODUCT_ID = re.compile(r"^(S2[ABC])_MSIL2A_(\d{8})T\d{6}_N\d{4}_R\d{3}_T(\d{2}[A-Z]{3})_")
EVALSCRIPT = """//VERSION=3
function setup() { return { input: ["B04", "B03", "B02", "dataMask"], output: { bands: 4 } }; }
function evaluatePixel(s) { return [2.5 * s.B04, 2.5 * s.B03, 2.5 * s.B02, s.dataMask]; }
"""

_lock = threading.Lock()
_token: Dict[str, Any] = {}


class CdseError(RuntimeError):
    pass


def configured(settings: Optional[Settings] = None) -> bool:
    cfg = settings or get_settings()
    return bool(cfg.cdse_client_id and cfg.cdse_client_secret)


def _access_token(cfg: Settings) -> str:
    """OAuth2 client-credentials token, cached until one minute before it expires."""
    if not configured(cfg):
        raise CdseError("identifiants Copernicus non configurés")
    client = (cfg.cdse_client_id, cfg.cdse_client_secret)
    with _lock:
        if _token.get("client") == client and _token.get("expires", 0) > time.monotonic():
            return _token["value"]
        try:
            response = httpx.post(cfg.cdse_token_url, data={
                "grant_type": "client_credentials", "client_id": client[0], "client_secret": client[1],
            }, headers={"User-Agent": USER_AGENT}, timeout=cfg.http_timeout)
        except Exception as exc:
            raise CdseError(f"service d'authentification injoignable ({type(exc).__name__})") from exc
        if response.status_code in (400, 401):
            raise CdseError("identifiants Copernicus refusés")
        if response.status_code >= 400:
            raise CdseError(f"authentification impossible (HTTP {response.status_code})")
        try:
            data = response.json()
            value, lifetime = str(data["access_token"]), int(data.get("expires_in") or 300)
        except Exception as exc:
            raise CdseError("réponse d'authentification inattendue") from exc
        _token.update(client=client, value=value, expires=time.monotonic() + max(lifetime - 60, 30))
        return _token["value"]


def _post(path: str, body: Dict[str, Any], cfg: Settings, accept: str = "application/json") -> httpx.Response:
    token = _access_token(cfg)
    try:
        response = httpx.post(f"{cfg.cdse_sh_url}{path}", json=body, timeout=cfg.http_timeout, headers={
            "User-Agent": USER_AGENT, "Authorization": f"Bearer {token}", "Accept": accept,
        })
    except Exception as exc:
        health.record(SOURCE, False, type(exc).__name__)
        raise CdseError(f"Sentinel Hub injoignable ({type(exc).__name__})") from exc
    if response.status_code == 401:
        with _lock:
            _token.clear()  # revoked / rotated client: next call asks for a new token
    if response.status_code >= 400:
        health.record(SOURCE, False, f"HTTP {response.status_code}")
        raise CdseError(f"Sentinel Hub : HTTP {response.status_code}")
    health.record(SOURCE, True)
    return response


def earth_search_id(product_id: str) -> Optional[str]:
    """CDSE product name -> Earth Search item identifier (None when not a Sentinel-2 L2A product)."""
    match = PRODUCT_ID.match(product_id or "")
    if not match:
        return None
    platform, day, tile = match.groups()
    return f"{platform}_{tile}_{day}_0_L2A"


def search(bbox: Sequence[float], start: datetime.datetime, end: datetime.datetime, max_cloud: float,
           settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    """Sentinel-2 L2A items (Earth Search-like: ``id``, ``geometry``, ``bbox``, ``properties``)."""
    cfg = settings or get_settings()
    body = {
        "collections": [COLLECTION],
        "bbox": list(bbox),
        "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}",
        "filter": f"eo:cloud_cover < {float(max_cloud)}",
        "filter-lang": "cql2-text",
        "limit": 100,
    }
    data = _post("/api/v1/catalog/1.0.0/search", body, cfg).json()
    items = []
    for feature in data.get("features") or []:
        item_id = earth_search_id(feature.get("id", ""))
        if not item_id:
            continue
        props = dict(feature.get("properties") or {})
        props.setdefault("grid:code", item_id.split("_")[1])
        props.setdefault("platform", f"sentinel-{item_id[1:3].lower()}")
        items.append({"id": item_id, "geometry": feature.get("geometry"), "bbox": feature.get("bbox"), "properties": props})
    return items


def render_tile(day: datetime.date, bounds_3857: Sequence[float], size: int = 256,
                settings: Optional[Settings] = None) -> bytes:
    """True-colour PNG (transparent where no data) of the acquisitions of ``day`` over the bounds."""
    cfg = settings or get_settings()
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=datetime.timezone.utc)
    body = {
        "input": {
            "bounds": {"bbox": list(bounds_3857), "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/3857"}},
            "data": [{"type": COLLECTION, "dataFilter": {
                "timeRange": {"from": start.isoformat().replace("+00:00", "Z"),
                              "to": (start + datetime.timedelta(days=1)).isoformat().replace("+00:00", "Z")},
                "mosaickingOrder": "leastCC",
            }}],
        },
        "output": {"width": size, "height": size, "responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
        "evalscript": EVALSCRIPT,
    }
    response = _post("/api/v1/process", body, cfg, accept="image/png")
    if not response.content.startswith(b"\x89PNG"):
        raise CdseError("réponse Sentinel Hub inattendue")
    return response.content


def check(settings: Optional[Settings] = None) -> str:
    """Live test (Administration): token, then one catalogue search over the territory."""
    cfg = settings or get_settings()
    end = datetime.datetime.now(datetime.timezone.utc)
    items = search(cfg.territory_bbox, end - datetime.timedelta(days=30), end, 100.0, cfg)
    return f"identifiants valides · {len(items)} scènes Sentinel-2 sur 30 jours"
