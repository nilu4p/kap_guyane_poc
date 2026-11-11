"""Operational settings editable by administrators at runtime (persisted, audited)."""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Dict, Optional

from app.config import DEFAULT_RADII_M, Settings, get_settings
from app.core import audit
from app.db import db, read_db

logger = logging.getLogger(__name__)

RADIUS_LABELS = {
    "ecole": "école maternelle / élémentaire", "college": "collège", "lycee": "lycée", "sante": "santé",
    "eau": "point d'eau potable", "alimentation": "commerce alimentaire", "transport": "transport",
    "services": "services publics", "petite_enfance": "petite enfance",
}

# name -> (type, min, max, label, explanation shown in the administration UI)
EDITABLE: Dict[str, Any] = {
    "data_refresh_days": (
        int, 0, 90, "Synchronisation automatique des données ouvertes (jours)",
        {"unit": "jours", "default": 7,
         "what": "Fréquence de la mise à jour automatique des statistiques INSEE, de l'annuaire de l'Éducation nationale et des équipements OpenStreetMap. 0 = uniquement à la demande.",
         "advice": "7 jours : l'INSEE et l'Éducation nationale publient au plus quelques fois par an, OSM change chaque jour."},
    ),
    "detour_factor": (
        float, 1.0, 2.5, "Facteur de détour (vol d'oiseau → trajet réel)",
        {"unit": "×", "default": 1.3,
         "what": "Multiplie les distances à vol d'oiseau pour estimer le trajet réel. La desserte compare ce trajet estimé au rayon "
                 "de chaque famille : avec 1,3, un rayon de 1 500 m correspond à environ 1 150 m à vol d'oiseau. 1 = vol d'oiseau pur.",
         "higher": "Desserte plus exigeante (zones de fleuve, de criques, réseau de pistes lâche).",
         "lower": "Desserte plus généreuse (centre urbain au maillage serré).",
         "advice": "1,3 en ville ; 1,6 à 2 en zone de criques, de fleuve ou de pistes."},
    ),
    "school_class_size": (
        int, 10, 35, "Écoles : effectif cible par classe (calcul des places)",
        {"unit": "élèves par classe", "default": 25,
         "what": "Places d'une école = nombre de classes (Éducation nationale) × cet effectif. La demande rattachée à une école au-delà de "
                 "ses places est comptée « sans place » (école saturée) et l'aide à l'implantation en tient compte. Une capacité saisie "
                 "en « places » dans l'écran Équipements remplace ce calcul.",
         "higher": "Écoles réputées plus capables : moins de saturation calculée.",
         "lower": "Saturation plus vite atteinte (classes dédoublées en éducation prioritaire : 12 en CP / CE1).",
         "advice": "25 en moyenne ; plus bas en réseau d'éducation prioritaire renforcée (REP+)."},
    ),
    "privacy_min_buildings": (
        int, 3, 50, "Secret : nombre minimal de bâtiments estimés par carreau exporté",
        {"unit": "bâtiments", "default": 5,
         "what": "Un carreau dont la croissance représente moins de bâtiments estimés n'est pas listé dans les exports (Recensement Éclaireur) : il est cumulé dans une ligne « autres carreaux ».",
         "advice": "5 au minimum (règle de la charte) ; augmenter dans les petites communes."},
    ),
    "s2_max_cloud": (
        float, 5.0, 80.0, "Sentinel-2 : couverture nuageuse maximale d'une scène (%)",
        {"unit": "%", "default": 40,
         "what": "Plafond de nuages des scènes Sentinel-2 retenues pour les composites de saison sèche (les nuages restants sont masqués pixel par pixel).",
         "advice": "40 % : en Guyane, abaisser trop le seuil laisse certaines années sans scène."},
    ),
    "s2_scenes_per_year": (
        int, 1, 10, "Sentinel-2 : scènes par saison sèche et par tuile",
        {"unit": "scènes", "default": 4,
         "what": "Nombre de scènes les plus claires combinées (médiane) pour chaque année. Plus de scènes = moins de bruit, analyse plus longue.",
         "advice": "4 à 6."},
    ),
    "max_analysis_area_km2": (
        float, 50.0, 5000.0, "Surface maximale analysée par commune (km²)",
        {"unit": "km²", "default": 900,
         "what": "Plafond de la surface lue dans les archives satellitaires pour une commune (zones habitées d'abord). Les petits écarts au-delà gardent la seule référence WSF 2019.",
         "advice": "900 km² couvrent les zones habitées de toutes les communes en une analyse de quelques minutes."},
    ),
    "fallback_persons_per_built_ha": (
        float, 5.0, 300.0, "Densité par défaut (habitants par hectare bâti)",
        {"unit": "hab./ha bâti", "default": 60,
         "what": "Utilisée seulement quand la densité ne peut pas être calibrée sur la population légale de la commune.",
         "advice": "Laisser la calibration faire ; ne sert qu'en secours."},
    ),
}
for _cat, _default in DEFAULT_RADII_M.items():
    EDITABLE[f"radius_{_cat}"] = (
        int, 100, 30000, f"Rayon de desserte — {RADIUS_LABELS.get(_cat, _cat)} (m)",
        {"unit": "mètres à vol d'oiseau", "default": _default,
         "what": f"Distance maximale à vol d'oiseau pour considérer un habitant desservi par un équipement « {RADIUS_LABELS.get(_cat, _cat)} ».",
         "advice": "Norme locale de la commune ; chaque résultat affiche le rayon utilisé."},
    )
EDITABLE["radius_lycee"] = (int, 100, 60000, "Rayon de desserte — lycée (m)",
                            {"unit": "mètres à vol d'oiseau", "default": 15000, "what": "Distance maximale pour un lycée.",
                             "advice": "Les lycées sont rares hors du littoral : rayon large."})


def _get(cfg: Settings, name: str) -> Any:
    if name.startswith("radius_"):
        return cfg.coverage_radii_m.get(name[len("radius_"):], EDITABLE[name][4]["default"])
    return getattr(cfg, name)


def _set(cfg: Settings, name: str, value: Any) -> None:
    if name.startswith("radius_"):
        cfg.coverage_radii_m = {**cfg.coverage_radii_m, name[len("radius_"):]: value}
    else:
        setattr(cfg, name, value)


def describe(settings: Optional[Settings] = None) -> Dict[str, Any]:
    cfg = settings or get_settings()
    return {
        name: {"value": _get(cfg, name), "type": kind.__name__, "min": low, "max": high, "label": label, **explanation}
        for name, (kind, low, high, label, explanation) in EDITABLE.items()
    }


def apply_stored(settings: Optional[Settings] = None) -> None:
    cfg = settings or get_settings()
    if "lycee" not in cfg.coverage_radii_m:
        cfg.coverage_radii_m = {**cfg.coverage_radii_m, "lycee": 15000}
    with read_db(cfg) as conn:
        stored = conn.execute("SELECT key, value FROM app_settings").fetchall()
    for record in stored:
        if record["key"] in EDITABLE:
            kind = EDITABLE[record["key"]][0]
            _set(cfg, record["key"], kind(json.loads(record["value"])))


def update(changes: Dict[str, Any], actor: str, settings: Optional[Settings] = None) -> Dict[str, Any]:
    cfg = settings or get_settings()
    validated: Dict[str, Any] = {}
    for name, value in changes.items():
        if name not in EDITABLE:
            raise ValueError(f"Paramètre non modifiable : {name}")
        kind, low, high, _label, _explanation = EDITABLE[name]
        try:
            typed = kind(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Valeur invalide pour {name}") from exc
        if not low <= typed <= high:
            raise ValueError(f"{name} doit être entre {low} et {high}")
        validated[name] = typed
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db(cfg) as conn:
        for name, value in validated.items():
            conn.execute(
                "INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, "
                "updated_by = excluded.updated_by",
                (name, json.dumps(value), now, actor),
            )
    for name, value in validated.items():
        _set(cfg, name, value)
    audit.record("system.settings", actor=actor, target="settings", details=validated, settings=cfg)
    return describe(cfg)
