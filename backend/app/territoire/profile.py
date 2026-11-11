"""Commune profiles: every indicator derived from the raw series, compared and ranked.

Each KPI states its formula, unit, year, source dataset and whether a higher value
is better or worse (used for colours only — the platform does not grade communes).
The same formula is applied to the department (Guyane) for comparison, and the
22 communes are ranked on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.config import Settings, get_settings
from app.territoire import store
from app.territoire.indicators import SOURCES

Series = Dict[str, Dict[int, float]]
Value = Optional[Tuple[float, int]]  # (value, year)

THEMES = {
    "demographie": "Démographie",
    "education": "Éducation",
    "sante": "Santé",
    "eau_logement": "Eau, énergie, logement",
    "emploi": "Emploi et formation",
    "alimentation": "Commerces alimentaires",
    "services": "Services et transport",
}


def last(s: Series, name: str) -> Value:
    values = s.get(name) or {}
    if not values:
        return None
    year = max(values)
    return values[year], year


def at(s: Series, name: str, year: int) -> Optional[float]:
    return (s.get(name) or {}).get(year)


def ratio(s: Series, num: Sequence[str], den: str, factor: float = 100.0, same_year: bool = True) -> Value:
    """Sum of ``num`` / ``den`` × factor, for the latest year where both exist."""
    years = set(s.get(den) or {})
    for n in num:
        years &= set(s.get(n) or {}) if same_year else years
    if not years:
        return None
    year = max(years)
    d = at(s, den, year)
    if not d:
        return None
    return sum(at(s, n, year) or 0.0 for n in num) / d * factor, year


def tcam(s: Series, name: str, span: int = 6) -> Value:
    values = s.get(name) or {}
    if not values:
        return None
    end = max(values)
    start = end - span
    if start not in values or not values[start]:
        return None
    return ((values[end] / values[start]) ** (1 / span) - 1) * 100, end


def evolution(s: Series, name: str, span: int = 5) -> Value:
    values = s.get(name) or {}
    if not values:
        return None
    end = max(values)
    start = end - span
    if start not in values or not values[start]:
        return None
    return (values[end] / values[start] - 1) * 100, end


def bpe_count(codes: Sequence[str]) -> Callable[[Series, Dict[str, Any]], Value]:
    def compute(s: Series, _c: Dict[str, Any]) -> Value:
        years = set()
        for code in codes:
            years |= set(s.get(f"bpe_{code}") or {})
        if not years:
            # No facility of these types: BPE lists non-zero counts only.
            any_bpe = [y for k, v in s.items() if k.startswith("bpe_") for y in v]
            return (0.0, max(any_bpe)) if any_bpe else None
        year = max(years)
        return sum(at(s, f"bpe_{c}", year) or 0.0 for c in codes), year
    return compute


def bpe_rate(codes: Sequence[str], per: float) -> Callable[[Series, Dict[str, Any]], Value]:
    count = bpe_count(codes)

    def compute(s: Series, c: Dict[str, Any]) -> Value:
        n = count(s, c)
        pop = last(s, "population")
        if n is None or not pop or not pop[0]:
            return None
        return n[0] / pop[0] * per, n[1]
    return compute


@dataclass(frozen=True)
class Kpi:
    id: str
    theme: str
    label: str
    unit: str
    compute: Callable[[Series, Dict[str, Any]], Value]
    sources: Tuple[str, ...]
    better: Optional[str] = None   # "higher" / "lower" / None
    formula: str = ""
    decimals: int = 1


def _density(s: Series, c: Dict[str, Any]) -> Value:
    pop = last(s, "population")
    if not pop or not c.get("surface_ha"):
        return None
    return pop[0] / (c["surface_ha"] / 100.0), pop[1]


def _natalite(s: Series, _c: Dict[str, Any]) -> Value:
    births, pops = s.get("naissances") or {}, s.get("population") or {}
    years = sorted(set(births) & set(pops))
    if not years:
        return None
    y = years[-1]
    return births[y] / pops[y] * 1000, y


KPIS: List[Kpi] = [
    Kpi("population", "demographie", "Population municipale légale", "habitants",
        lambda s, c: last(s, "population"), ("DS_POPULATIONS_HISTORIQUES",), None, "Population municipale INSEE (millésime)", 0),
    Kpi("croissance_pop", "demographie", "Croissance annuelle moyenne sur 6 ans", "% par an",
        lambda s, c: tcam(s, "population", 6), ("DS_POPULATIONS_HISTORIQUES",), None, "TCAM entre N−6 et N", 2),
    Kpi("densite", "demographie", "Densité de population", "hab./km²", _density,
        ("DS_POPULATIONS_HISTORIQUES",), None, "population / surface (IGN)", 1),
    Kpi("naissances", "demographie", "Naissances domiciliées", "par an",
        lambda s, c: last(s, "naissances"), ("DS_ETAT_CIVIL_NAIS_COMMUNES",), None, "État civil, lieu de domicile de la mère", 0),
    Kpi("natalite", "demographie", "Taux de natalité", "‰", _natalite,
        ("DS_ETAT_CIVIL_NAIS_COMMUNES", "DS_POPULATIONS_HISTORIQUES"), None, "naissances / population × 1 000", 1),
    Kpi("part_moins_15", "demographie", "Part des moins de 15 ans", "%",
        lambda s, c: ratio(s, ["rp_pop_moins_15"], "rp_pop_total"), ("DS_RP_POPULATION_PRINC",), None, "recensement", 1),
    Kpi("part_65_plus", "demographie", "Part des 65 ans ou plus", "%",
        lambda s, c: ratio(s, ["rp_pop_65_plus"], "rp_pop_total"), ("DS_RP_POPULATION_PRINC",), None, "recensement", 1),
    Kpi("eleves_1er_degre", "education", "Élèves des écoles publiques du 1er degré", "élèves",
        lambda s, c: last(s, "ecoles_pub_eleves"), ("EDUCATION_EFFECTIFS",), None, "rentrée la plus récente", 0),
    Kpi("evol_eleves", "education", "Évolution des élèves sur 5 rentrées", "%",
        lambda s, c: evolution(s, "ecoles_pub_eleves", 5), ("EDUCATION_EFFECTIFS",), None, "écoles publiques", 1),
    Kpi("eleves_par_classe", "education", "Élèves par classe (écoles publiques)", "élèves",
        lambda s, c: ratio(s, ["ecoles_pub_eleves"], "ecoles_pub_classes", 1.0), ("EDUCATION_EFFECTIFS",), "lower", "élèves / classes", 1),
    Kpi("scol_3_5", "education", "Scolarisation des 2-5 ans", "%",
        lambda s, c: ratio(s, ["rp_scolarises_2_5"], "rp_age_2_5"), ("DS_RP_EDUCATION_PRINC",), "higher", "inscrits / population de l'âge", 1),
    Kpi("scol_6_10", "education", "Scolarisation des 6-10 ans", "%",
        lambda s, c: ratio(s, ["rp_scolarises_6_10"], "rp_age_6_10"), ("DS_RP_EDUCATION_PRINC",), "higher", "inscrits / population de l'âge", 1),
    Kpi("scol_11_14", "education", "Scolarisation des 11-14 ans", "%",
        lambda s, c: ratio(s, ["rp_scolarises_11_14"], "rp_age_11_14"), ("DS_RP_EDUCATION_PRINC",), "higher", "inscrits / population de l'âge", 1),
    Kpi("scol_15_17", "education", "Scolarisation des 15-17 ans", "%",
        lambda s, c: ratio(s, ["rp_scolarises_15_17"], "rp_age_15_17"), ("DS_RP_EDUCATION_PRINC",), "higher", "inscrits / population de l'âge", 1),
    Kpi("ecoles", "education", "Écoles (maternelles, élémentaires, primaires)", "établissements",
        bpe_count(["C107", "C108", "C109"]), ("DS_BPE",), None, "BPE", 0),
    Kpi("colleges", "education", "Collèges", "établissements", bpe_count(["C201"]), ("DS_BPE",), None, "BPE", 0),
    Kpi("medecins", "sante", "Médecins généralistes", "pour 10 000 hab.", bpe_rate(["D265"], 10_000),
        ("DS_BPE", "DS_POPULATIONS_HISTORIQUES"), "higher", "BPE D265 / population × 10 000", 1),
    Kpi("medecins_n", "sante", "Médecins généralistes (nombre)", "professionnels", bpe_count(["D265"]), ("DS_BPE",), None, "BPE D265", 0),
    Kpi("infirmiers", "sante", "Infirmiers libéraux", "pour 10 000 hab.", bpe_rate(["D281"], 10_000),
        ("DS_BPE", "DS_POPULATIONS_HISTORIQUES"), "higher", "BPE D281", 1),
    Kpi("sages_femmes", "sante", "Sages-femmes", "pour 10 000 hab.", bpe_rate(["D278"], 10_000),
        ("DS_BPE", "DS_POPULATIONS_HISTORIQUES"), "higher", "BPE D278", 1),
    Kpi("dentistes", "sante", "Chirurgiens-dentistes", "pour 10 000 hab.", bpe_rate(["D277"], 10_000),
        ("DS_BPE", "DS_POPULATIONS_HISTORIQUES"), "higher", "BPE D277", 1),
    Kpi("pharmacies", "sante", "Pharmacies", "pour 10 000 hab.", bpe_rate(["D307"], 10_000),
        ("DS_BPE", "DS_POPULATIONS_HISTORIQUES"), "higher", "BPE D307", 1),
    Kpi("centres_sante", "sante", "Centres et maisons de santé", "structures", bpe_count(["D108", "D113"]), ("DS_BPE",), None, "BPE D108 + D113", 0),
    Kpi("pmi", "sante", "Services de PMI", "structures", bpe_count(["D115"]), ("DS_BPE",), None, "BPE D115", 0),
    Kpi("urgences", "sante", "Services d'urgences", "structures", bpe_count(["D106"]), ("DS_BPE",), None, "BPE D106", 0),
    Kpi("sans_electricite", "eau_logement", "Résidences principales sans électricité", "%",
        lambda s, c: ratio(s, ["rp_sans_electricite"], "rp_residences"), ("DS_RP_LOGEMENT_DOM_PRINC",), "lower", "recensement", 1),
    Kpi("eau_froide_sans_point", "eau_logement", "Sans point d'eau intérieur ou eau froide seulement", "%",
        lambda s, c: ratio(s, ["rp_eau_froide_ou_sans_point_eau"], "rp_residences"), ("DS_RP_LOGEMENT_DOM_PRINC",), "lower",
        "recensement — modalité INSEE « aucun point d'eau ou eau froide seulement »", 1),
    Kpi("eaux_usees_sol", "eau_logement", "Eaux usées évacuées à même le sol", "%",
        lambda s, c: ratio(s, ["rp_eaux_usees_sol"], "rp_residences"), ("DS_RP_LOGEMENT_DOM_PRINC",), "lower", "recensement", 1),
    Kpi("tout_egout", "eau_logement", "Raccordées au tout-à-l'égout", "%",
        lambda s, c: ratio(s, ["rp_tout_egout"], "rp_residences"), ("DS_RP_LOGEMENT_DOM_PRINC",), "higher", "recensement", 1),
    Kpi("habitat_precaire", "eau_logement", "Habitations de fortune ou cases traditionnelles", "%",
        lambda s, c: ratio(s, ["rp_habitat_fortune", "rp_cases_traditionnelles"], "rp_residences"), ("DS_RP_LOGEMENT_DOM_PRINC",),
        "lower", "recensement", 1),
    Kpi("sans_bain_wc", "eau_logement", "Sans baignoire / douche et WC", "%",
        lambda s, c: ratio(s, ["rp_sans_bain_wc"], "rp_residences"), ("DS_RP_LOGEMENT_DOM_PRINC",), "lower", "recensement", 1),
    Kpi("residences", "eau_logement", "Résidences principales", "logements",
        lambda s, c: last(s, "rp_residences"), ("DS_RP_LOGEMENT_DOM_PRINC",), None, "recensement", 0),
    Kpi("chomage", "emploi", "Taux de chômage des 15-64 ans (recensement)", "%",
        lambda s, c: ratio(s, ["rp_chomeurs_15_64"], "rp_actifs_15_64"), ("DS_RP_EMPLOI_LR_PRINC",), "lower",
        "chômeurs / actifs, au sens du recensement", 1),
    Kpi("chomage_jeunes", "emploi", "Taux de chômage des 15-24 ans (recensement)", "%",
        lambda s, c: ratio(s, ["rp_chomeurs_15_24"], "rp_actifs_15_24"), ("DS_RP_EMPLOI_LR_PRINC",), "lower", "recensement", 1),
    Kpi("activite", "emploi", "Taux d'activité des 15-64 ans", "%",
        lambda s, c: ratio(s, ["rp_actifs_15_64"], "rp_pop_15_64"), ("DS_RP_EMPLOI_LR_PRINC",), "higher", "actifs / population", 1),
    Kpi("sans_diplome", "emploi", "15-64 ans sans diplôme ou avec le CEP", "%",
        lambda s, c: ratio(s, ["rp_sans_diplome_15_64"], "rp_pop_15_64"), ("DS_RP_EMPLOI_LR_PRINC",), "lower",
        "y compris élèves et étudiants", 1),
    Kpi("commerces_alim", "alimentation", "Commerces alimentaires", "pour 1 000 hab.",
        bpe_rate(["B104", "B105", "B201", "B202", "B204", "B205", "B206", "B207", "B208", "B210"], 1_000),
        ("DS_BPE", "DS_POPULATIONS_HISTORIQUES"), "higher", "BPE B104-B105, B201-B210", 2),
    Kpi("grandes_surfaces", "alimentation", "Hypermarchés et supermarchés", "magasins", bpe_count(["B104", "B105"]), ("DS_BPE",), None, "BPE", 0),
    Kpi("superettes_epiceries", "alimentation", "Supérettes et épiceries", "magasins", bpe_count(["B201", "B202"]), ("DS_BPE",), None, "BPE", 0),
    Kpi("boulangeries", "alimentation", "Boulangeries-pâtisseries", "magasins", bpe_count(["B207"]), ("DS_BPE",), None, "BPE", 0),
    Kpi("france_services", "services", "Espaces France services", "points", bpe_count(["A128"]), ("DS_BPE",), None, "BPE A128", 0),
    Kpi("poste", "services", "Bureaux, relais et agences postales", "points", bpe_count(["A206", "A207", "A208"]), ("DS_BPE",), None, "BPE", 0),
    Kpi("france_travail", "services", "Agences France Travail", "points", bpe_count(["A122"]), ("DS_BPE",), None, "BPE A122", 0),
    Kpi("securite", "services", "Gendarmerie et police", "points", bpe_count(["A104", "A140"]), ("DS_BPE",), None, "BPE", 0),
    Kpi("petite_enfance", "services", "Accueil du jeune enfant (EAJE)", "structures", bpe_count(["D502"]), ("DS_BPE",), None, "BPE D502", 0),
    Kpi("transport", "services", "Taxis, aéroport et gares", "équipements", bpe_count(["E101", "E102", "E107", "E108", "E109"]),
        ("DS_BPE",), None, "BPE E1", 0),
]
KPI_BY_ID = {k.id: k for k in KPIS}


def _compute(kpi: Kpi, s: Series, c: Dict[str, Any]) -> Value:
    try:
        return kpi.compute(s, c)
    except (ZeroDivisionError, TypeError, ValueError):
        return None


def kpi_table(settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Every KPI for every commune and the department (comparisons, maps, rankings)."""
    cfg = settings or get_settings()
    communes = store.communes(cfg)
    dep = {"code": cfg.department_code, "nom": "Guyane", "surface_ha": sum(c.get("surface_ha") or 0 for c in communes)}
    all_series = store.series_by_geo(cfg)
    values: Dict[str, Dict[str, Any]] = {}
    for c in communes + [dep]:
        s = all_series.get(c["code"], {})
        values[c["code"]] = {}
        for kpi in KPIS:
            v = _compute(kpi, s, c)
            if v is not None:
                values[c["code"]][kpi.id] = {"value": round(v[0], kpi.decimals), "year": v[1]}
    return {"communes": communes, "department": dep, "values": values}


def describe_kpis() -> List[Dict[str, Any]]:
    return [{"id": k.id, "theme": k.theme, "theme_label": THEMES[k.theme], "label": k.label, "unit": k.unit, "better": k.better,
             "formula": k.formula, "decimals": k.decimals, "sources": [SOURCES.get(s, s) for s in k.sources]} for k in KPIS]


def profile(code: str, settings: Optional[Settings] = None, table: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Full profile of a commune: KPIs by theme with Guyane value and rank, key series, hypothesis."""
    cfg = settings or get_settings()
    commune = store.commune(code, cfg)
    if commune is None:
        return None
    table = table or kpi_table(cfg)
    vals = table["values"]
    dep_code = cfg.department_code
    codes = [c["code"] for c in table["communes"]]
    themes: Dict[str, List[Dict[str, Any]]] = {t: [] for t in THEMES}
    for kpi in KPIS:
        mine = vals.get(code, {}).get(kpi.id)
        dep = vals.get(dep_code, {}).get(kpi.id)
        ranked = sorted((vals[c][kpi.id]["value"], c) for c in codes if kpi.id in vals.get(c, {}))
        rank = None
        if mine is not None and ranked:
            order = list(reversed(ranked)) if kpi.better != "lower" else ranked
            rank = next(i for i, (_v, c) in enumerate(order, start=1) if c == code)
        themes[kpi.theme].append({
            "id": kpi.id, "label": kpi.label, "unit": kpi.unit, "better": kpi.better, "formula": kpi.formula,
            "decimals": kpi.decimals, "value": mine["value"] if mine else None, "year": mine["year"] if mine else None,
            "guyane": dep["value"] if dep else None, "rank": rank, "ranked": len(ranked),
            "sources": [SOURCES.get(s, s) for s in kpi.sources],
        })
    s = store.series(code, ("population", "naissances", "ecoles_pub_eleves", "ecoles_pub_classes", "deces"), cfg)
    commune.pop("contour", None)
    return {
        "commune": commune,
        "themes": [{"id": t, "label": THEMES[t], "kpis": items} for t, items in themes.items()],
        "series": {k: [{"year": y, "value": v} for y, v in sorted(vs.items())] for k, vs in s.items()},
        "hypothesis": store.hypothesis(code, cfg),
        "equipments": store.equipment_counts(cfg).get(code, {}),
        "notes": [
            "Les indicateurs du recensement (logement, emploi, scolarisation) décrivent le millésime indiqué ; "
            "en Guyane, les communes de 10 000 habitants ou plus sont recensées par sondage annuel (8 % des logements).",
            "FiLoSoFi (revenus, pauvreté) n'est pas diffusé pour les communes de Guyane : aucun indicateur de revenu n'est affiché.",
            "La BPE recense des équipements déclarés : la présence d'un équipement ne dit rien de sa capacité ni de son accessibilité.",
        ],
    }
