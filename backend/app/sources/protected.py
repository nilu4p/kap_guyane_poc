"""Protected areas from the World Database on Protected Areas (UNEP-WCMC / IUCN), keyless.

In French Guiana: the Parc amazonien de Guyane, national and regional nature
reserves (Nouragues, Trinité, Kaw-Roura, Amana, Mont Grand Matoury…), biological
reserves, conservatoire du littoral sites… Used as a *siting constraint*, with two levels:

- **stricte** — IUCN Ia, Ib, II, III, IV and national / regional nature reserves, biological
  reserves, a national park's core: building is (nearly) excluded; such cells can be
  removed from the candidates;
- **encadrée** — IUCN V / VI, regional natural park, national park adhesion area, Ramsar
  wetland: inhabited territories where building is possible under rules; the site is
  only flagged for attention. (The regional natural park "Guyane" and the Parc amazonien
  adhesion area cover whole communes: excluding them would exclude the bourgs themselves.)

When the UNEP-WCMC map server fails and a Protected Planet token is configured
(Administration › Paramètres › Clés API des sources), the same areas are read from the
Protected Planet API (country GUF) before falling back to the stale cache.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Sequence

import httpx

from app.config import Settings, get_settings
from app.sources import health
from app.sources.http import USER_AGENT, cache_read, cache_read_stale, cache_write, get_json

logger = logging.getLogger(__name__)

FIELDS = "site_id,name,desig,desig_eng,iucn_cat,realm,status,status_yr,iso3"
TTL = 30 * 24 * 3600
PP_SOURCE = "protected_planet"
PP_MAX_PAGES = 10


class ProtectedPlanetError(RuntimeError):
    pass


def areas(bbox: Optional[Sequence[float]] = None, settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    """Protected-area features intersecting ``bbox`` (GeoJSON features, cached 30 days)."""
    cfg = settings or get_settings()
    west, south, east, north = bbox or cfg.territory_bbox
    key = f"{west:.3f},{south:.3f},{east:.3f},{north:.3f}"
    cached = cache_read("wdpa", key, TTL, cfg)
    if cached is None:
        payload = get_json(
            cfg.wdpa_url,
            params={
                "geometry": f"{west},{south},{east},{north}", "geometryType": "esriGeometryEnvelope", "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects", "outFields": FIELDS, "returnGeometry": "true",
                "outSR": "4326", "maxAllowableOffset": "0.003", "f": "geojson",
            },
            settings=cfg, source="wdpa",
        )
        if payload and isinstance(payload.get("features"), list):
            cached = [f for f in payload["features"] if f.get("geometry") and (f.get("properties") or {}).get("iso3", "FRA") in ("FRA", "GUF", "")]
            cache_write("wdpa", key, cached, cfg)
        elif cfg.protected_planet_token:
            try:
                cached = [f for f in protected_planet_features(cfg) if _bbox_overlaps(f["geometry"], (west, south, east, north))]
                cache_write("wdpa", key, cached, cfg)
            except ProtectedPlanetError as exc:
                logger.warning("Protected Planet fallback failed: %s", exc)
                cached = cache_read_stale("wdpa", key, cfg) or []
        else:
            cached = cache_read_stale("wdpa", key, cfg) or []
    out = []
    for feature in cached:
        props = feature.get("properties") or {}
        designation = _clean(props.get("desig") or props.get("desig_eng") or "")
        iucn = str(props.get("iucn_cat") or "")
        out.append({
            "type": "Feature", "geometry": feature["geometry"],
            "properties": {"name": _clean(props.get("name") or ""), "designation": designation, "iucn": iucn,
                           "status_year": props.get("status_yr"), "level": level(iucn, designation)},
        })
    return out


STRICT_IUCN = {"Ia", "Ib", "II", "III", "IV"}
FRAMED_WORDS = ("adhésion", "adhesion", "parc naturel régional", "ramsar", "wetland")
STRICT_WORDS = ("réserve naturelle", "réserve biologique", "coeur", "cœur", "arrêté de protection")


def level(iucn: str, designation: str) -> str:
    """'stricte' or 'encadrée' (see the module docstring)."""
    text = designation.lower()
    if any(w in text for w in FRAMED_WORDS):
        return "encadrée"
    if iucn in STRICT_IUCN or any(w in text for w in STRICT_WORDS):
        return "stricte"
    return "encadrée"


def _clean(text: str) -> str:
    """WDPA texts carry escaped quotes ("D\\'Adhésion"): plain text only."""
    return str(text).replace("\\'", "'").replace("\\", "").strip()


def _pp_get(path: str, cfg: Settings, **params: Any) -> Dict[str, Any]:
    """GET on the Protected Planet API. The token travels in the query string: never log the URL."""
    try:
        response = httpx.get(f"{cfg.protected_planet_url}{path}", params={**params, "token": cfg.protected_planet_token},
                             headers={"User-Agent": USER_AGENT}, timeout=cfg.http_timeout)
    except Exception as exc:
        health.record(PP_SOURCE, False, type(exc).__name__)
        raise ProtectedPlanetError(f"API injoignable ({type(exc).__name__})") from exc
    if response.status_code >= 400:
        health.record(PP_SOURCE, False, f"HTTP {response.status_code}")
        raise ProtectedPlanetError("jeton refusé" if response.status_code in (401, 403) else f"HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        health.record(PP_SOURCE, False, "réponse non JSON")
        raise ProtectedPlanetError("réponse non JSON") from exc
    health.record(PP_SOURCE, True)
    return data


def _pp_pages(cfg: Settings, with_geometry: bool = True, per_page: int = 50) -> Iterator[List[Dict[str, Any]]]:
    for page in range(1, PP_MAX_PAGES + 1):
        batch = _pp_get("/protected_areas/search", cfg, country="GUF", with_geometry=str(with_geometry).lower(),
                        per_page=per_page, page=page).get("protected_areas") or []
        yield batch
        if len(batch) < per_page:
            return


def protected_planet_features(settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    """Every protected area of French Guiana from Protected Planet, in the WDPA map-server field names."""
    cfg = settings or get_settings()
    out = []
    for batch in _pp_pages(cfg):
        for area in batch:
            geojson = area.get("geojson") or {}
            geometry = geojson.get("geometry") if geojson.get("type") == "Feature" else geojson
            if not (isinstance(geometry, dict) and geometry.get("type")):
                continue
            status_date = str(area.get("legal_status_updated_at") or "")
            year = next((int(part) for part in status_date.replace("-", "/").split("/") if len(part) == 4 and part.isdigit()), None)
            out.append({"type": "Feature", "geometry": geometry, "properties": {
                "site_id": area.get("wdpa_id") or area.get("id"), "name": area.get("name") or "",
                "desig": (area.get("designation") or {}).get("name") or "",
                "iucn_cat": (area.get("iucn_category") or {}).get("name") or "", "status_yr": year, "iso3": "GUF",
            }})
    return out


def _bbox_overlaps(geometry: Dict[str, Any], bbox: Sequence[float]) -> bool:
    lons, lats = [], []

    def walk(coords: Any) -> None:
        if coords and isinstance(coords[0], (int, float)):
            lons.append(coords[0])
            lats.append(coords[1])
        else:
            for part in coords or []:
                walk(part)

    walk(geometry.get("coordinates"))
    if not lons:
        return False
    west, south, east, north = bbox
    return min(lons) <= east and max(lons) >= west and min(lats) <= north and max(lats) >= south


def check(settings: Optional[Settings] = None) -> str:
    """Live test (Administration): one page of the protected areas of French Guiana."""
    cfg = settings or get_settings()
    if not cfg.protected_planet_token:
        raise ProtectedPlanetError("jeton Protected Planet non configuré")
    batch = next(_pp_pages(cfg, with_geometry=False, per_page=50))
    return f"jeton valide · {len(batch)}{'+' if len(batch) == 50 else ''} aires protégées en Guyane"
