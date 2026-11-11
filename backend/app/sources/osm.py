"""Everyday facilities and roads from OpenStreetMap (Overpass API, ODbL), keyless.

Families mapped to OSM tags (points, or way / relation centres):

| Family | OSM tags |
| --- | --- |
| ``sante`` | amenity = hospital, clinic, doctors, dentist, pharmacy · healthcare = * |
| ``eau`` | amenity = drinking_water, water_point · man_made = water_tap, water_well |
| ``alimentation`` | shop = supermarket, convenience, general, grocery, greengrocer, butcher, bakery, seafood, frozen_food · amenity = marketplace |
| ``transport`` | highway = bus_stop · amenity = bus_station, ferry_terminal, taxi · public_transport = station · aeroway = aerodrome |
| ``services`` | amenity = townhall, post_office, police, community_centre, social_facility, library, courthouse · office = government |
| ``petite_enfance`` | amenity = childcare |

OSM completeness varies a lot in French Guiana: the platform says so next to every
OSM-based figure, and the services can add the missing facilities themselves.
Schools come from the Éducation nationale directory instead (authoritative).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from app.config import Settings, get_settings
from app.sources import health
from app.sources.http import USER_AGENT, cache_read, cache_read_stale, cache_write

logger = logging.getLogger(__name__)

TTL = 7 * 24 * 3600
ROAD_TTL = 30 * 24 * 3600

FAMILY_FILTERS: Dict[str, List[str]] = {
    "sante": ['["amenity"~"^(hospital|clinic|doctors|dentist|pharmacy)$"]', '["healthcare"]'],
    "eau": ['["amenity"~"^(drinking_water|water_point)$"]', '["man_made"~"^(water_tap|water_well)$"]'],
    "alimentation": ['["shop"~"^(supermarket|convenience|general|grocery|greengrocer|butcher|bakery|seafood|frozen_food)$"]',
                     '["amenity"="marketplace"]'],
    "transport": ['["highway"="bus_stop"]', '["amenity"~"^(bus_station|ferry_terminal|taxi)$"]',
                  '["public_transport"="station"]', '["aeroway"="aerodrome"]'],
    "services": ['["amenity"~"^(townhall|post_office|police|community_centre|social_facility|library|courthouse)$"]',
                 '["office"="government"]'],
    "petite_enfance": ['["amenity"="childcare"]'],
}
ROAD_CLASSES = ("motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|track|road")


class OverpassError(RuntimeError):
    pass


def _overpass(query: str, cfg: Settings) -> Dict[str, Any]:
    try:
        response = httpx.post(cfg.overpass_url, data={"data": query}, headers={"User-Agent": USER_AGENT},
                              timeout=max(cfg.http_timeout, 200.0))
    except httpx.HTTPError as exc:
        health.record("openstreetmap", False, type(exc).__name__)
        raise OverpassError(f"Overpass injoignable ({type(exc).__name__})") from exc
    if response.status_code >= 400:
        health.record("openstreetmap", False, f"HTTP {response.status_code}")
        raise OverpassError(f"Overpass HTTP {response.status_code}")
    data = response.json()
    # On timeout or memory exhaustion Overpass still answers 200 with *partial* elements and a
    # "remark": such an answer must never be taken for the complete map (it would delete facilities).
    remark = str(data.get("remark") or "")
    if remark:
        health.record("openstreetmap", False, f"réponse partielle : {remark[:120]}")
        raise OverpassError(f"Overpass a renvoyé une réponse partielle ({remark[:160]})")
    health.record("openstreetmap", True)
    return data


def _bbox(bbox: Sequence[float]) -> str:
    west, south, east, north = bbox
    return f"{south:.4f},{west:.4f},{north:.4f},{east:.4f}"


def classify(tags: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """(family, subtype) of an OSM element, None if it is not a facility we track."""
    amenity, shop, healthcare = tags.get("amenity", ""), tags.get("shop", ""), tags.get("healthcare", "")
    man_made = tags.get("man_made", "")
    if amenity in ("hospital", "clinic", "doctors", "dentist", "pharmacy"):
        return "sante", amenity
    if healthcare:
        return "sante", healthcare
    if amenity in ("drinking_water", "water_point") or man_made in ("water_tap", "water_well"):
        return "eau", amenity or man_made
    if shop in ("supermarket", "convenience", "general", "grocery", "greengrocer", "butcher", "bakery", "seafood", "frozen_food"):
        return "alimentation", shop
    if amenity == "marketplace":
        return "alimentation", "marketplace"
    if tags.get("highway") == "bus_stop":
        return "transport", "bus_stop"
    if amenity in ("bus_station", "ferry_terminal", "taxi"):
        return "transport", amenity
    if tags.get("public_transport") == "station":
        return "transport", "station"
    if tags.get("aeroway") == "aerodrome":
        return "transport", "aerodrome"
    if amenity in ("townhall", "post_office", "police", "community_centre", "social_facility", "library", "courthouse"):
        return "services", amenity
    if tags.get("office") == "government":
        return "services", "government"
    if amenity == "childcare":
        return "petite_enfance", "childcare"
    return None


def facilities(settings: Optional[Settings] = None, live: bool = True,
               bbox: Optional[Sequence[float]] = None) -> List[Dict[str, Any]]:
    """Every tracked facility in the territory (one dict per OSM element)."""
    cfg = settings or get_settings()
    area = _bbox(bbox or cfg.territory_bbox)
    parts = "".join(f"nwr{f}({area});" for filters in FAMILY_FILTERS.values() for f in filters)
    query = f"[out:json][timeout:180];({parts});out center tags;"
    data = cache_read("osm", query, TTL, cfg) if live else None
    if data is None:
        try:
            if not live:
                raise OverpassError("hors ligne")
            data = _overpass(query, cfg)
            cache_write("osm", query, data, cfg)
        except OverpassError:
            data = cache_read_stale("osm", query, cfg)
            if data is None:
                raise
    out = []
    for element in data.get("elements") or []:
        tags = element.get("tags") or {}
        kind = classify(tags)
        lat = element.get("lat", (element.get("center") or {}).get("lat"))
        lon = element.get("lon", (element.get("center") or {}).get("lon"))
        if not kind or lat is None or lon is None:
            continue
        out.append({
            "uid": f"osm:{element['type']}/{element['id']}",
            "category": kind[0], "subtype": kind[1],
            "name": tags.get("name") or tags.get("operator") or "",
            "lat": float(lat), "lon": float(lon),
            "attributes": {k: v for k, v in tags.items() if k in ("opening_hours", "operator", "healthcare:speciality", "ref", "addr:street")},
        })
    return out


def roads(bbox: Sequence[float], settings: Optional[Settings] = None, live: bool = True) -> List[List[Tuple[float, float]]]:
    """Road centre lines inside ``bbox`` as lists of (lon, lat) — used for 'served by a road' checks."""
    cfg = settings or get_settings()
    query = f'[out:json][timeout:180];way["highway"~"^({ROAD_CLASSES})$"]({_bbox(bbox)});out geom;'
    data = cache_read("osm_roads", query, ROAD_TTL, cfg) if live else None
    if data is None:
        try:
            if not live:
                raise OverpassError("hors ligne")
            data = _overpass(query, cfg)
            cache_write("osm_roads", query, data, cfg)
        except OverpassError:
            data = cache_read_stale("osm_roads", query, cfg)
            if data is None:
                raise
    lines = []
    for element in data.get("elements") or []:
        geometry = element.get("geometry") or []
        if len(geometry) >= 2:
            lines.append([(float(p["lon"]), float(p["lat"])) for p in geometry])
    return lines
