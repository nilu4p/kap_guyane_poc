"""Schools of French Guiana from the Éducation nationale open data (OpenDataSoft API), keyless.

- ``fr-en-annuaire-education``: every open school, collège and lycée with its
  coordinates (UAI, public / private, nature, priority education network);
- ``fr-en-ecoles-effectifs-nb_classes``: pupils and classes of each *public*
  primary school, per school year since 2009 — the series behind "how many
  pupils did the commune gain" and the capacity of each school on the map.

Whole-department exports (a few thousand records) are cached a week.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import Settings, get_settings
from app.sources.http import cache_read, cache_read_stale, cache_write, get_json

logger = logging.getLogger(__name__)

TTL = 7 * 24 * 3600
ANNUAIRE = "fr-en-annuaire-education"
EFFECTIFS = "fr-en-ecoles-effectifs-nb_classes"


class EducationError(RuntimeError):
    pass


def _export(dataset: str, where: str, select: str, cfg: Settings, live: bool) -> List[Dict[str, Any]]:
    url = f"{cfg.education_api_url}/catalog/datasets/{dataset}/exports/json"
    key = f"{dataset}|{where}|{select}"
    if live:
        cached = cache_read("education", key, TTL, cfg)
        if cached is not None:
            return cached
        data = get_json(url, params={"where": where, "select": select}, settings=cfg, source="education_nationale")
        if isinstance(data, list):
            cache_write("education", key, data, cfg)
            return data
    stale = cache_read_stale("education", key, cfg)
    if stale is not None:
        return stale
    raise EducationError(f"{dataset} injoignable et aucune copie locale")


def _year(value: Any) -> Optional[int]:
    text = str(value or "")[:4]
    return int(text) if text.isdigit() else None


def schools(settings: Optional[Settings] = None, live: bool = True) -> List[Dict[str, Any]]:
    """Open establishments with coordinates: one dict per UAI."""
    cfg = settings or get_settings()
    rows = _export(
        ANNUAIRE, f'code_departement="{cfg.department_code}" and etat="OUVERT"',
        "identifiant_de_l_etablissement,nom_etablissement,type_etablissement,statut_public_prive,code_commune,"
        "nom_commune,latitude,longitude,libelle_nature,ecole_maternelle,ecole_elementaire,"
        "appartenance_education_prioritaire,precision_localisation,date_ouverture",
        cfg, live,
    )
    out = []
    for r in rows:
        lat, lon = r.get("latitude"), r.get("longitude")
        if lat is None or lon is None:
            continue
        out.append({
            "uai": r.get("identifiant_de_l_etablissement"),
            "name": r.get("nom_etablissement") or "",
            "type": r.get("type_etablissement") or "",
            "nature": r.get("libelle_nature") or "",
            "public": (r.get("statut_public_prive") or "").lower().startswith("public"),
            "commune": r.get("code_commune"),
            "lat": float(lat), "lon": float(lon),
            "maternelle": bool(r.get("ecole_maternelle")), "elementaire": bool(r.get("ecole_elementaire")),
            "education_prioritaire": r.get("appartenance_education_prioritaire") or "",
            "precision": r.get("precision_localisation") or "",
            "opened": r.get("date_ouverture"),
        })
    return out


def commune_resolver(settings: Optional[Settings] = None, live: bool = True) -> Any:
    """(uai, raw code) → INSEE commune code.

    The enrolment dataset fills ``code_commune_insee`` with the *postal* code for many
    Guiana schools (97320 for Saint-Laurent…): the school directory (UAI → commune) is
    authoritative, the official postal codes of each commune are the fallback.
    """
    from app.sources import geoapi

    cfg = settings or get_settings()
    by_uai: Dict[str, str] = {}
    try:
        by_uai = {s["uai"]: s["commune"] for s in schools(cfg, live) if s.get("uai") and s.get("commune")}
    except EducationError:
        pass
    postal: Dict[str, str] = {}
    insee = set()
    for feature in geoapi.bundled()["features"]:
        props = feature["properties"]
        insee.add(props["code"])
        for cp in props.get("codesPostaux") or []:
            postal.setdefault(cp, props["code"])

    def resolve(uai: Optional[str], raw: Optional[str]) -> Optional[str]:
        if uai and uai in by_uai:
            return by_uai[uai]
        if raw in insee:
            return raw
        return postal.get(raw or "")

    return resolve


def enrolments(settings: Optional[Settings] = None, live: bool = True) -> List[Dict[str, Any]]:
    """Pupils and classes of each public primary school, every school year (one dict per school-year)."""
    cfg = settings or get_settings()
    resolve = commune_resolver(cfg, live)
    rows = _export(
        EFFECTIFS, f'code_departement="{cfg.department_code}"',
        "rentree_scolaire,code_commune_insee,numero_ecole,denomination_principale,patronyme,nombre_total_classes,"
        "nombre_total_eleves,nombre_eleves_preelementaire_hors_ulis,nombre_eleves_elementaire_hors_ulis,rep,rep_plus",
        cfg, live,
    )
    out = []
    for r in rows:
        year = _year(r.get("rentree_scolaire"))
        if year is None:
            continue
        out.append({
            "year": year,
            "commune": resolve(r.get("numero_ecole"), r.get("code_commune_insee")),
            "uai": r.get("numero_ecole"),
            "name": " ".join(x for x in (r.get("denomination_principale"), r.get("patronyme")) if x and x != "-"),
            "eleves": r.get("nombre_total_eleves") or 0,
            "classes": r.get("nombre_total_classes") or 0,
            "preelementaire": r.get("nombre_eleves_preelementaire_hors_ulis") or 0,
            "elementaire": r.get("nombre_eleves_elementaire_hors_ulis") or 0,
            "rep_plus": str(r.get("rep_plus") or "0") == "1",
        })
    return out


def latest_by_school(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Most recent school year of each school (UAI -> record, with the previous years' pupils)."""
    by_school: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        if r.get("uai"):
            by_school.setdefault(r["uai"], []).append(r)
    out = {}
    for uai, items in by_school.items():
        items.sort(key=lambda r: r["year"])
        last = dict(items[-1])
        last["history"] = {r["year"]: r["eleves"] for r in items}
        out[uai] = last
    return out
