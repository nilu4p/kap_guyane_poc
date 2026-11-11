"""Runtime configuration loaded from environment / `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent

# Coverage radius (metres, straight line) used by default for each equipment family.
# Planning rules of thumb, editable in Administration › Paramètres; every result shows
# the radius it used, so a different local standard is a setting, not a code change.
DEFAULT_RADII_M: Dict[str, int] = {
    "ecole": 1500,          # école maternelle / élémentaire : trajet à pied d'un enfant
    "college": 5000,
    "sante": 5000,          # médecin, centre / maison de santé, pharmacie
    "eau": 500,             # borne-fontaine, point d'eau potable
    "alimentation": 1000,   # épicerie, supérette, marché
    "transport": 500,       # arrêt de bus, gare routière, dégrad
    "services": 3000,       # mairie annexe, France services, poste
    "petite_enfance": 2000,
}


class Settings(BaseSettings):
    """Application settings for the KAP Guyane platform."""

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    app_name: str = "KAP Guyane"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    # "production" disables the interactive API docs. Secure cookies are a separate switch.
    environment: str = "development"

    # Notifications (Slack / Mattermost / Teams compatible JSON webhook).
    alert_webhook_url: str = ""

    # Optional API keys of data sources (also editable in Administration › Paramètres,
    # encrypted at rest). Every source works keyless; a key adds a fallback provider.
    # Copernicus Data Space Ecosystem (Sentinel Hub OAuth client): Sentinel-2 catalogue and
    # imagery when Earth Search (AWS) is unreachable.
    cdse_client_id: str = ""
    cdse_client_secret: str = ""
    # Protected Planet API token: WDPA protected areas when the UNEP-WCMC map server fails.
    protected_planet_token: str = ""

    # --- Infrastructure ----------------------------------------------------
    # Empty DATABASE_URL = embedded SQLite in DATA_DIR (development, tests, single host).
    database_url: str = ""
    database_password_file: str = ""
    database_pool_size: int = 10
    redis_url: str = ""
    redis_password_file: str = ""
    celery_broker_url: str = ""
    # "inline": the API process also runs the scheduler and the analyses (one container).
    # "workers": Celery workers / beat do it (scalable deployment).
    background_mode: str = "inline"

    # --- Security ---------------------------------------------------------
    master_key: str = ""
    master_key_file: str = ""
    bootstrap_admin_user: str = "admin"
    bootstrap_admin_password: str = ""
    session_ttl_minutes: int = 8 * 60
    session_idle_minutes: int = 30
    cookie_secure: bool = False
    password_min_length: int = 12
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    rate_limit_per_minute: int = 600
    trusted_proxies: List[str] = Field(default_factory=lambda: ["127.0.0.1", "172.16.0.0/12", "::1"])
    allow_insecure_webhooks: bool = False
    webhook_allowed_hosts: List[str] = Field(default_factory=list)
    custom_source_allowed_hosts: List[str] = Field(default_factory=list)
    custom_source_max_mb: int = 20
    public_url: str = "http://localhost:8080"

    keys_dir: Path = _REPO_ROOT / "keys"
    cache_dir: Path = _REPO_ROOT / "cache"
    data_dir: Path = _REPO_ROOT / "data"
    backup_dir: Path = _REPO_ROOT / "backups"
    http_timeout: float = 30.0

    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ]
    )

    # --- Territory ---------------------------------------------------------
    department_code: str = "973"
    # French Guiana bounding box (lon/lat): catalogue searches and map framing.
    territory_bbox: Tuple[float, float, float, float] = (-54.62, 2.11, -51.61, 5.78)
    # Pilot commune shown first (Saint-Laurent-du-Maroni, see the PoC brief).
    default_commune: str = "97311"

    # Open data endpoints (keyless).
    geo_api_url: str = "https://geo.api.gouv.fr"
    melodi_url: str = "https://api.insee.fr/melodi"
    education_api_url: str = "https://data.education.gouv.fr/api/explore/v2.1"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    stac_url: str = "https://earth-search.aws.element84.com/v1"
    wsf2019_url: str = "https://download.geoservice.dlr.de/WSF2019/files"
    wsf_evolution_url: str = "https://download.geoservice.dlr.de/WSF_EVO/files"
    ms_buildings_index_url: str = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
    wdpa_url: str = (
        "https://data-gis.unep-wcmc.org/server/rest/services/ProtectedSites/"
        "The_World_Database_of_Protected_Areas/MapServer/1/query"
    )
    # Keyed fallbacks (used only once the matching key is configured).
    cdse_token_url: str = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    cdse_sh_url: str = "https://sh.dataspace.copernicus.eu"
    protected_planet_url: str = "https://api.protectedplanet.net/v3"
    # Open data re-synchronised automatically every N days (0 = manual only).
    data_refresh_days: int = 7

    # --- Spatial analysis --------------------------------------------------
    # Aggregation grid. 200 m is the floor set by the ethics charter: nothing finer is
    # ever stored, displayed or exported (no individual building can be designated).
    grid_cell_m: int = 200
    # Exports suppress cells whose estimated new buildings are below this count
    # (same idea as statistical secrecy: a cell must not point at one household).
    privacy_min_buildings: int = 5
    # Straight-line distance × detour factor ≈ distance along the paths actually walked. Coverage
    # compares this estimated trip with the radius of each family.
    detour_factor: float = 1.3
    # School places = classes × this target class size (capacity-aware coverage of schools).
    school_class_size: int = 25
    coverage_radii_m: Dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_RADII_M))
    # Sentinel-2 dry-season composites (built-up change after the WSF 2019 reference).
    s2_season_start_month: int = 8          # August → December: least cloudy months on the coast
    s2_season_end_month: int = 12
    s2_max_cloud: float = 40.0              # scene cloud cover ceiling (%)
    s2_scenes_per_year: int = 4             # best scenes kept per dry season (median composite)
    s2_first_year: int = 2016
    # Persons per hectare of built surface: calibrated per commune on the INSEE legal
    # population; this value is only the fallback when no calibration is possible.
    fallback_persons_per_built_ha: float = 60.0
    # Largest window (km²) read from the satellite archives for one commune: interior
    # communes are mostly forest, only their settled areas are analysed.
    max_analysis_area_km2: float = 900.0

    # --- Reports -------------------------------------------------------------
    report_originator: str = "Cellule d'aide à la décision territoriale — KAP Guyane"
    report_classification: str = "DOCUMENT DE TRAVAIL — USAGE DES SERVICES"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
