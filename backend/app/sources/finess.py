"""Health establishments from FINESS (Ministry of Health, Licence Ouverte), keyless.

Read from the public OpenDataSoft mirror of the Etalab FINESS extract (geocoded
establishments, refreshed from data.gouv.fr). Only *care* establishments are kept
(hospitals, health centres and houses, pharmacies, PMI, laboratories, dialysis, mental
health centres…): social and medico-social facilities (child welfare, disability
services…) are out of scope of the "santé" family.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import Settings, get_settings
from app.sources.http import cache_read, cache_read_stale, cache_write, get_json

logger = logging.getLogger(__name__)

DATASET = "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/healthref-france-finess/exports/json"
DEPARTMENT = "9C"  # FINESS code of French Guiana
TTL = 7 * 24 * 3600

# FINESS establishment category → subtype shown in the platform.
CARE_CATEGORIES: Dict[str, str] = {
    "101": "centre hospitalier régional", "355": "centre hospitalier", "365": "établissement de soins pluridisciplinaire",
    "129": "établissement de soins médicaux", "109": "soins de suite et de réadaptation", "362": "soins de longue durée",
    "124": "centre de santé", "603": "maison de santé", "223": "PMI", "228": "centre de santé sexuelle",
    "620": "pharmacie", "627": "propharmacie", "611": "laboratoire", "141": "centre de dialyse",
    "146": "dialyse ambulatoire", "156": "centre médico-psychologique", "127": "hospitalisation à domicile",
}


class FinessError(RuntimeError):
    pass


def establishments(settings: Optional[Settings] = None, live: bool = True) -> List[Dict[str, Any]]:
    cfg = settings or get_settings()
    where = f'dep_code="{DEPARTMENT}"'
    key = f"finess:{where}"
    rows = cache_read("finess", key, TTL, cfg) if live else None
    if rows is None:
        if live:
            rows = get_json(DATASET, params={"where": where, "select": "nofinesset,rs,rslongue,categetab,libcategetab,com_code,coord,datemaj_structure"},
                            settings=cfg, source="finess")
        if isinstance(rows, list):
            cache_write("finess", key, rows, cfg)
        else:
            rows = cache_read_stale("finess", key, cfg)
    if rows is None:
        raise FinessError("FINESS injoignable et aucune copie locale")
    out = []
    for r in rows:
        category = str(r.get("categetab") or "")
        coord = r.get("coord") or {}
        if category not in CARE_CATEGORIES or coord.get("lat") is None or coord.get("lon") is None:
            continue
        out.append({
            "uid": f"finess:{r.get('nofinesset')}", "category": "sante", "subtype": CARE_CATEGORIES[category],
            "name": (r.get("rslongue") or r.get("rs") or "").strip(), "lat": float(coord["lat"]), "lon": float(coord["lon"]),
            "attributes": {"finess": r.get("nofinesset"), "categorie": r.get("libcategetab"), "maj": r.get("datemaj_structure")},
        })
    return out
