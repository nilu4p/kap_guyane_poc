"""INSEE statistics through the Melodi API (api.insee.fr/melodi), keyless.

Melodi serves INSEE datasets as SDMX-like observations: each observation has
``dimensions`` (GEO, TIME_PERIOD, AGE…) and a measure ``OBS_VALUE_NIVEAU``.
Several geographies are requested at once (``GEO=COM-97311&GEO=DEP-973``), and
dimension filters narrow the answer; results are paged (``paging.next``).

GEO identifiers come back prefixed by the vintage of the geography
(``2026-COM-97311``): :func:`geo_code` keeps the code (``97311`` / ``973``).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx

from app.config import Settings, get_settings
from app.sources import health
from app.sources.http import USER_AGENT, cache_read, cache_read_stale, cache_write

logger = logging.getLogger(__name__)

TTL = 7 * 24 * 3600
MAX_PAGES = 20


class MelodiError(RuntimeError):
    pass


def geo_code(raw: str) -> str:
    """``2026-COM-97311`` → ``97311``; ``2025-DEP-973`` → ``973``."""
    return raw.rsplit("-", 1)[-1]


def geo_params(commune_codes: Sequence[str], department: str) -> List[str]:
    return [f"COM-{c}" for c in commune_codes] + [f"DEP-{department}"]


def observations(dataset: str, params: Dict[str, Any], settings: Optional[Settings] = None,
                 live: bool = True) -> List[Dict[str, Any]]:
    """All observations of ``dataset`` matching ``params`` (cached a week, stale copy on failure)."""
    cfg = settings or get_settings()
    key = f"{dataset}?{sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in params.items())}"
    if live:
        cached = cache_read("melodi", key, TTL, cfg)
        if cached is not None:
            return cached
    else:
        stale = cache_read_stale("melodi", key, cfg)
        if stale is not None:
            return stale
        raise MelodiError("hors ligne : aucune copie locale")
    url: Optional[str] = f"{cfg.melodi_url}/data/{dataset}"
    query: Optional[Dict[str, Any]] = {**params, "maxResult": 10000}
    result: List[Dict[str, Any]] = []
    try:
        with httpx.Client(timeout=max(cfg.http_timeout, 60.0), headers={"User-Agent": USER_AGENT}) as client:
            for _page in range(MAX_PAGES):
                if url is None:
                    break
                response = client.get(url, params=query)
                if response.status_code == 429:  # anonymous quota: wait once, then retry
                    time.sleep(5)
                    response = client.get(url, params=query)
                if response.status_code >= 400:
                    raise MelodiError(f"{dataset} : HTTP {response.status_code}")
                data = response.json()
                result.extend(data.get("observations") or [])
                url, query = (data.get("paging") or {}).get("next"), None
    except (httpx.HTTPError, ValueError, MelodiError) as exc:
        health.record("insee_melodi", False, f"{dataset}: {type(exc).__name__}")
        stale = cache_read_stale("melodi", key, cfg)
        if stale is not None:
            logger.warning("Melodi %s unreachable (%s): stale cached copy used", dataset, exc)
            return stale
        raise MelodiError(f"{dataset} injoignable ({type(exc).__name__})") from exc
    health.record("insee_melodi", True)
    cache_write("melodi", key, result, cfg)
    return result


def select(obs: Iterable[Dict[str, Any]], **filters: str) -> List[Dict[str, Any]]:
    """Observations whose dimensions equal every ``filters`` value."""
    out = []
    for o in obs:
        dims = o.get("dimensions") or {}
        if all(dims.get(k) == v for k, v in filters.items()):
            out.append(o)
    return out


def value(o: Dict[str, Any]) -> Optional[float]:
    measure = (o.get("measures") or {}).get("OBS_VALUE_NIVEAU") or {}
    v = measure.get("value")
    return float(v) if isinstance(v, (int, float)) else None


def by_geo_year(obs: Iterable[Dict[str, Any]]) -> Dict[str, Dict[int, float]]:
    """{geo code: {year: value}} (values of identical keys are summed)."""
    out: Dict[str, Dict[int, float]] = {}
    for o in obs:
        dims = o.get("dimensions") or {}
        v = value(o)
        if v is None or "GEO" not in dims or not str(dims.get("TIME_PERIOD", "")).isdigit():
            continue
        series = out.setdefault(geo_code(dims["GEO"]), {})
        year = int(dims["TIME_PERIOD"])
        series[year] = series.get(year, 0.0) + v
    return out


def codelist(dataset: str, settings: Optional[Settings] = None) -> Dict[str, Dict[str, str]]:
    """{concept: {code: French label}} of a dataset (GEO excluded), cached 30 days."""
    cfg = settings or get_settings()
    cached = cache_read("melodi_range", dataset, 30 * 24 * 3600, cfg)
    if cached is not None:
        return cached
    try:
        response = httpx.get(f"{cfg.melodi_url}/range/{dataset}", headers={"User-Agent": USER_AGENT},
                             timeout=max(cfg.http_timeout, 90.0))
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        stale = cache_read_stale("melodi_range", dataset, cfg)
        if stale is not None:
            return stale
        raise MelodiError(f"nomenclature {dataset} injoignable ({type(exc).__name__})") from exc
    out: Dict[str, Dict[str, str]] = {}
    for concept in data.get("range") or []:
        code = (concept.get("concept") or {}).get("code")
        if not code or code == "GEO":
            continue
        out[code] = {v["code"]: ((v.get("label") or {}).get("fr") or v["code"]) for v in concept.get("values") or []}
    cache_write("melodi_range", dataset, out, cfg)
    return out
