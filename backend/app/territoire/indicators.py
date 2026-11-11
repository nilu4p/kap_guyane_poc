"""Raw statistical series of the communes, fetched from INSEE (Melodi) and the
Éducation nationale open data, stored as ``(geo, indicator, year, value, source)``.

Only *raw counts* are stored (population, dwellings without electricity, general
practitioners…); rates and ratios are derived when a profile is built
(:mod:`app.territoire.profile`), so a definition can never drift between screens.

Every series names its dataset: the platform never shows a figure without its source.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.config import Settings, get_settings
from app.sources import education, melodi

logger = logging.getLogger(__name__)

Row = Tuple[str, str, int, float, str]  # geo, indicator, year, value, source

# dataset -> human readable source (shown under every figure)
SOURCES: Dict[str, str] = {
    "DS_POPULATIONS_HISTORIQUES": "INSEE — Populations municipales légales (Melodi DS_POPULATIONS_HISTORIQUES)",
    "DS_ETAT_CIVIL_NAIS_COMMUNES": "INSEE — État civil, naissances domiciliées (Melodi DS_ETAT_CIVIL_NAIS_COMMUNES)",
    "DS_ETAT_CIVIL_DECES_COMMUNES": "INSEE — État civil, décès domiciliés (Melodi DS_ETAT_CIVIL_DECES_COMMUNES)",
    "DS_RP_POPULATION_PRINC": "INSEE — Recensement, population par âge (Melodi DS_RP_POPULATION_PRINC)",
    "DS_RP_EDUCATION_PRINC": "INSEE — Recensement, scolarisation par âge (Melodi DS_RP_EDUCATION_PRINC)",
    "DS_RP_LOGEMENT_DOM_PRINC": "INSEE — Recensement, logements dans les DOM (Melodi DS_RP_LOGEMENT_DOM_PRINC)",
    "DS_RP_EMPLOI_LR_PRINC": "INSEE — Recensement, population active et chômage (Melodi DS_RP_EMPLOI_LR_PRINC)",
    "DS_BPE": "INSEE — Base permanente des équipements (Melodi DS_BPE)",
    "EDUCATION_EFFECTIFS": "Éducation nationale — Effectifs et classes des écoles publiques du 1er degré (data.education.gouv.fr)",
}

# Census dimension slices for the overseas dwellings dataset: indicator -> non-total dimension.
LOGEMENT_SLICES: Dict[str, Optional[Tuple[str, str]]] = {
    "rp_residences": None,
    "rp_sans_electricite": ("ELEC", "0"),
    "rp_eau_froide_ou_sans_point_eau": ("WSS", "1_3"),
    "rp_eaux_usees_sol": ("WW", "0"),
    "rp_tout_egout": ("WW", "1"),
    "rp_fosse_septique": ("WW", "2"),
    "rp_habitat_fortune": ("TDW", "5"),
    "rp_cases_traditionnelles": ("TDW", "7"),
    "rp_maisons_bois": ("TDW", "1_2_W"),
    "rp_sans_bain_wc": ("BAINWC", "0"),
    "rp_climatisation": ("AIRCOND", "1"),
}
LOGEMENT_DIMS = ("WW", "AIRCOND", "ELEC", "BAINWC", "TDW", "WSS", "SOBO")

AGE_SLICES = {"_T": "rp_pop_total", "Y_LT15": "rp_pop_moins_15", "Y15T24": "rp_pop_15_24", "Y25T39": "rp_pop_25_39",
              "Y40T54": "rp_pop_40_54", "Y55T64": "rp_pop_55_64", "Y_GE65": "rp_pop_65_plus"}
SCHOOL_AGES = {"Y2T5": "2_5", "Y6T10": "6_10", "Y11T14": "11_14", "Y15T17": "15_17", "Y18T24": "18_24"}
EMPLOI_SLICES = {
    # indicator: (AGE, EMPSTA_ENQ, EDUC)
    "rp_pop_15_64": ("Y15T64", "_T", "_T"),
    "rp_actifs_15_64": ("Y15T64", "1T2", "_T"),
    "rp_actifs_occupes_15_64": ("Y15T64", "1", "_T"),
    "rp_chomeurs_15_64": ("Y15T64", "2", "_T"),
    "rp_actifs_15_24": ("Y15T24", "1T2", "_T"),
    "rp_chomeurs_15_24": ("Y15T24", "2", "_T"),
    "rp_sans_diplome_15_64": ("Y15T64", "_T", "001T100_RP"),
}


def _rows(series: Dict[str, Dict[int, float]], indicator: str, source: str) -> List[Row]:
    return [(geo, indicator, year, value, source) for geo, years in series.items() for year, value in years.items()]


def _populations(geo: List[str], cfg: Settings, live: bool) -> List[Row]:
    obs = melodi.observations("DS_POPULATIONS_HISTORIQUES", {"GEO": geo, "POPREF_MEASURE": "PMUN"}, cfg, live)
    return _rows(melodi.by_geo_year(obs), "population", "DS_POPULATIONS_HISTORIQUES")


def _etat_civil(geo: List[str], cfg: Settings, live: bool) -> List[Row]:
    rows = _rows(melodi.by_geo_year(melodi.observations(
        "DS_ETAT_CIVIL_NAIS_COMMUNES", {"GEO": geo, "EC_MEASURE": "LVB"}, cfg, live)), "naissances", "DS_ETAT_CIVIL_NAIS_COMMUNES")
    rows += _rows(melodi.by_geo_year(melodi.observations(
        "DS_ETAT_CIVIL_DECES_COMMUNES", {"GEO": geo, "EC_MEASURE": "DTH"}, cfg, live)), "deces", "DS_ETAT_CIVIL_DECES_COMMUNES")
    return rows


def _ages(geo: List[str], cfg: Settings, live: bool) -> List[Row]:
    obs = melodi.observations("DS_RP_POPULATION_PRINC", {"GEO": geo, "SEX": "_T", "RP_MEASURE": "POP"}, cfg, live)
    rows: List[Row] = []
    for age, indicator in AGE_SLICES.items():
        rows += _rows(melodi.by_geo_year(melodi.select(obs, AGE=age)), indicator, "DS_RP_POPULATION_PRINC")
    return rows


def _schooling(geo: List[str], cfg: Settings, live: bool) -> List[Row]:
    obs = melodi.observations("DS_RP_EDUCATION_PRINC", {"GEO": geo, "SEX": "_T", "RP_MEASURE": "POP"}, cfg, live)
    rows: List[Row] = []
    for age, suffix in SCHOOL_AGES.items():
        rows += _rows(melodi.by_geo_year(melodi.select(obs, AGE=age, STUD="_T")), f"rp_age_{suffix}", "DS_RP_EDUCATION_PRINC")
        rows += _rows(melodi.by_geo_year(melodi.select(obs, AGE=age, STUD="1")), f"rp_scolarises_{suffix}", "DS_RP_EDUCATION_PRINC")
    return rows


def _logement(geo: List[str], cfg: Settings, live: bool) -> List[Row]:
    obs = melodi.observations("DS_RP_LOGEMENT_DOM_PRINC", {"GEO": geo, "OCS": "DW_MAIN", "RP_MEASURE": "DWELLINGS"}, cfg, live)
    rows: List[Row] = []
    for indicator, slice_ in LOGEMENT_SLICES.items():
        filters = {dim: "_T" for dim in LOGEMENT_DIMS}
        if slice_:
            filters[slice_[0]] = slice_[1]
        rows += _rows(melodi.by_geo_year(melodi.select(obs, **filters)), indicator, "DS_RP_LOGEMENT_DOM_PRINC")
    return rows


def _emploi(geo: List[str], cfg: Settings, live: bool) -> List[Row]:
    obs = melodi.observations("DS_RP_EMPLOI_LR_PRINC", {"GEO": geo, "SEX": "_T", "RP_MEASURE": "POP"}, cfg, live)
    rows: List[Row] = []
    for indicator, (age, status, educ) in EMPLOI_SLICES.items():
        rows += _rows(melodi.by_geo_year(melodi.select(obs, AGE=age, EMPSTA_ENQ=status, EDUC=educ)), indicator,
                      "DS_RP_EMPLOI_LR_PRINC")
    return rows


def _equipements(geo: List[str], cfg: Settings, live: bool) -> List[Row]:
    obs = melodi.observations("DS_BPE", {"GEO": geo, "BPE_MEASURE": "FACILITIES"}, cfg, live)
    rows: List[Row] = []
    for o in obs:
        dims = o.get("dimensions") or {}
        v = melodi.value(o)
        ftype = dims.get("FACILITY_TYPE")
        if v is None or not ftype or ftype == "_T" or not str(dims.get("TIME_PERIOD", "")).isdigit():
            continue
        rows.append((melodi.geo_code(dims["GEO"]), f"bpe_{ftype}", int(dims["TIME_PERIOD"]), v, "DS_BPE"))
    return rows


def _ecoles(communes: Sequence[str], cfg: Settings, live: bool) -> List[Row]:
    records = education.enrolments(cfg, live=live)
    totals: Dict[Tuple[str, str, int], float] = {}
    for r in records:
        commune, year = r.get("commune"), r.get("year")
        if not commune or year is None:
            continue
        for geo in (commune, cfg.department_code):
            for indicator, value in (("ecoles_pub_nb", 1), ("ecoles_pub_eleves", r.get("eleves") or 0),
                                     ("ecoles_pub_classes", r.get("classes") or 0),
                                     ("ecoles_pub_eleves_preelementaire", r.get("preelementaire") or 0),
                                     ("ecoles_pub_eleves_elementaire", r.get("elementaire") or 0)):
                key = (geo, indicator, year)
                totals[key] = totals.get(key, 0.0) + float(value)
    return [(geo, ind, year, value, "EDUCATION_EFFECTIFS") for (geo, ind, year), value in totals.items()]


FETCHERS: List[Tuple[str, Callable[..., List[Row]]]] = [
    ("Populations légales", _populations),
    ("État civil", _etat_civil),
    ("Âges (recensement)", _ages),
    ("Scolarisation (recensement)", _schooling),
    ("Logement DOM (recensement)", _logement),
    ("Activité et chômage (recensement)", _emploi),
    ("Équipements (BPE)", _equipements),
]


def fetch_all(commune_codes: Sequence[str], settings: Optional[Settings] = None, live: bool = True,
              progress: Optional[Callable[[str, bool, str], None]] = None) -> Tuple[List[Row], List[Dict[str, Any]]]:
    """Every series for the communes + the department. Returns (rows, per-dataset report).

    A failing dataset does not stop the others: its report says why, and the
    previous values stay in the database.
    """
    cfg = settings or get_settings()
    geo = melodi.geo_params(commune_codes, cfg.department_code)
    rows: List[Row] = []
    report: List[Dict[str, Any]] = []
    steps: List[Tuple[str, Callable[[], List[Row]]]] = [(label, (lambda f=f: f(geo, cfg, live))) for label, f in FETCHERS]
    steps.append(("Effectifs des écoles (Éducation nationale)", lambda: _ecoles(commune_codes, cfg, live)))
    for label, job in steps:
        try:
            got = job()
            rows += got
            report.append({"dataset": label, "ok": True, "rows": len(got)})
            if progress:
                progress(label, True, f"{len(got)} valeurs")
        except Exception as exc:  # one dataset down must not block the others
            logger.warning("Indicator dataset %s failed: %s", label, exc)
            report.append({"dataset": label, "ok": False, "error": str(exc)[:200]})
            if progress:
                progress(label, False, str(exc)[:120])
    return rows, report


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
