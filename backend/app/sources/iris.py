"""IRIS (infra-communal statistical units) of the larger communes: contours and census figures.

- **Contours** — IGN Géoplateforme WFS ``STATISTICALUNITS.IRISGE:iris_ge`` (keyless).
- **Population by age** — INSEE Melodi ``DS_RP_POPULATION_PRINC_IRIS`` (keyless).

The two geographies may differ in vintage (IGN publishes the current split, the census
figures use the split of their own year: in Saint-Laurent-du-Maroni some IRIS were divided
since). Only IRIS present in both are used individually; the rest of the commune forms a
*residual zone* calibrated on the remaining population, so the commune total is preserved.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import Settings, get_settings
from app.core.geo import simplify_geometry
from app.sources import melodi
from app.sources.http import cache_read, cache_read_stale, cache_write, get_json

logger = logging.getLogger(__name__)

WFS = "https://data.geopf.fr/wfs/ows"
LAYER = "STATISTICALUNITS.IRISGE:iris_ge"
TTL = 90 * 24 * 3600
AGES = ("_T", "Y2T5", "Y6T10", "Y11T14", "Y15T17", "Y_LT15")


class IrisError(RuntimeError):
    pass


def contours(commune: str, settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    """IRIS polygons of a commune (code, name, type, simplified geometry)."""
    cfg = settings or get_settings()
    key = f"iris:{commune}"
    data = cache_read("iris", key, TTL, cfg)
    if data is None:
        data = get_json(WFS, params={"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": LAYER,
                                     "OUTPUTFORMAT": "application/json", "CQL_FILTER": f"code_insee='{commune}'"},
                        settings=cfg, source="ign_iris")
        if data and isinstance(data.get("features"), list):
            cache_write("iris", key, data, cfg)
        else:
            data = cache_read_stale("iris", key, cfg)
    if not data:
        raise IrisError("contours IRIS injoignables")
    out = []
    for f in data.get("features") or []:
        props = f.get("properties") or {}
        if props.get("code_iris") and f.get("geometry"):
            out.append({"code": props["code_iris"], "nom": props.get("nom_iris") or props["code_iris"],
                        "type": props.get("type_iris") or "", "geometry": simplify_geometry(f["geometry"], 0.0005)})
    return out


def populations(codes: List[str], settings: Optional[Settings] = None) -> Dict[str, Any]:
    """{"year": census year, "iris": {code: {age: persons}}} for the IRIS codes known to the census."""
    cfg = settings or get_settings()
    obs = melodi.observations("DS_RP_POPULATION_PRINC_IRIS",
                              {"GEO": [f"IRIS-{c}" for c in codes], "SEX": "_T", "IMMI": "_T", "NATIONALITY_TYPE": "_T",
                               "HAR": "_T", "RP_MEASURE": "POP"}, cfg)
    years = sorted({int(o["dimensions"]["TIME_PERIOD"]) for o in obs if str(o["dimensions"].get("TIME_PERIOD", "")).isdigit()})
    if not years:
        return {"year": None, "iris": {}}
    year = years[-1]
    out: Dict[str, Dict[str, float]] = {}
    for o in obs:
        dims = o["dimensions"]
        value = melodi.value(o)
        if value is None or dims.get("TIME_PERIOD") != str(year) or dims.get("AGE") not in AGES:
            continue
        out.setdefault(melodi.geo_code(dims["GEO"]), {})[dims["AGE"]] = value
    return {"year": year, "iris": out}


def commune_layer(commune: str, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    """IRIS of a commune with their census figures, or None when the commune is a single IRIS."""
    cfg = settings or get_settings()
    zones = contours(commune, cfg)
    if len(zones) < 2:
        return None
    pops = populations([z["code"] for z in zones], cfg)
    matched = []
    for z in zones:
        figures = pops["iris"].get(z["code"])
        if figures and figures.get("_T"):
            matched.append({**z, "ages": figures})
    return {"year": pops["year"], "zones": matched, "unmatched": [z for z in zones if z["code"] not in pops["iris"]],
            "source": "IGN Géoplateforme (contours IRIS) · INSEE Melodi DS_RP_POPULATION_PRINC_IRIS"}
