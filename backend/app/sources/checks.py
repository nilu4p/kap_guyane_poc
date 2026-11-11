"""Live checks of the integrated sources (Administration › Sources, button « Tester »)."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

import httpx

from app.config import Settings, get_settings
from app.sources import health
from app.sources.http import USER_AGENT


def _get(url: str, cfg: Settings, **params: Any) -> httpx.Response:
    return httpx.get(url, params=params or None, headers={"User-Agent": USER_AGENT}, timeout=cfg.http_timeout, follow_redirects=True)


def _geo(cfg: Settings) -> str:
    r = _get(f"{cfg.geo_api_url}/departements/{cfg.department_code}/communes", cfg, fields="nom")
    r.raise_for_status()
    return f"{len(r.json())} communes"


def _melodi(cfg: Settings) -> str:
    r = _get(f"{cfg.melodi_url}/data/DS_POPULATIONS_HISTORIQUES", cfg, GEO=f"DEP-{cfg.department_code}", TIME_PERIOD="2023")
    r.raise_for_status()
    obs = r.json().get("observations") or []
    value = obs[0]["measures"]["OBS_VALUE_NIVEAU"]["value"] if obs else None
    return f"population légale 2023 de la Guyane : {int(value):,}".replace(",", " ") if value else "réponse vide"


def _education(cfg: Settings) -> str:
    r = _get(f"{cfg.education_api_url}/catalog/datasets/fr-en-annuaire-education/records", cfg,
             where=f'code_departement="{cfg.department_code}"', limit=1)
    r.raise_for_status()
    return f"{r.json().get('total_count')} établissements dans l'annuaire"


def _overpass(cfg: Settings) -> str:
    r = httpx.post(cfg.overpass_url, data={"data": "[out:json][timeout:20];node(5.49,-54.04,5.51,-54.02);out count;"},
                   headers={"User-Agent": USER_AGENT}, timeout=cfg.http_timeout)
    r.raise_for_status()
    return "Overpass répond"


def _stac(cfg: Settings) -> str:
    r = _get(f"{cfg.stac_url}/collections/sentinel-2-l2a", cfg)
    r.raise_for_status()
    return "collection Sentinel-2 L2A disponible"


def _wsf(cfg: Settings) -> str:
    r = httpx.head(f"{cfg.wsf2019_url}/WSF2019_v1_-54_4.tif", headers={"User-Agent": USER_AGENT}, timeout=cfg.http_timeout)
    r.raise_for_status()
    return f"tuile WSF 2019 accessible ({int(r.headers.get('content-length', 0)) // 1_000_000} Mo)"


def _cdse(cfg: Settings) -> str:
    from app.sources import cdse

    return cdse.check(cfg)


def _protected_planet(cfg: Settings) -> str:
    from app.sources import protected

    return protected.check(cfg)


CHECKS: Dict[str, Callable[[Settings], str]] = {
    "geo.api.gouv.fr": _geo, "insee_melodi": _melodi, "education_nationale": _education,
    "openstreetmap": _overpass, "sentinel2": _stac, "dlr_wsf2019": _wsf,
    # keyed providers (Administration › Paramètres › Clés API des sources)
    "copernicus_cdse": _cdse, "protected_planet": _protected_planet,
}


def check_service(service: str, settings: Optional[Settings] = None) -> Dict[str, Any]:
    cfg = settings or get_settings()
    started = time.monotonic()
    try:
        message = CHECKS[service](cfg)
        ok = True
    except Exception as exc:
        message, ok = f"{type(exc).__name__}: {str(exc)[:160]}", False
    health.record(service, ok, "" if ok else message)
    return {"ok": ok, "message": message, "latency_ms": round((time.monotonic() - started) * 1000)}
