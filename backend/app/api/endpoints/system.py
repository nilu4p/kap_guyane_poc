"""Administration: webhook and source API keys (write-only, encrypted), runtime settings, source health, catalogue, supervision."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import admin, request_ip, viewer
from app.config import get_settings
from app.core import audit, credentials
from app.services import notify, runtime
from app.services.notify import WebhookRejected, validate_webhook_url
from app.sources import health
from app.sources.checks import CHECKS, check_service

router = APIRouter(tags=["system"])

_MAX = credentials.MAX_VALUE_LENGTH


class KeysUpdate(BaseModel):
    """Only present fields change; an empty string removes the dashboard value."""

    alert_webhook_url: Optional[str] = Field(None, max_length=_MAX)
    cdse_client_id: Optional[str] = Field(None, max_length=_MAX)
    cdse_client_secret: Optional[str] = Field(None, max_length=_MAX)
    protected_planet_token: Optional[str] = Field(None, max_length=_MAX)


@router.get("/settings/keys")
def get_keys(_user: Dict[str, Any] = Depends(admin)) -> Dict[str, Any]:
    """Credential status (configured / origin / masked hint) — never the values."""
    return {"keys": credentials.describe()}


@router.put("/settings/keys")
def put_keys(body: KeysUpdate, request: Request, user: Dict[str, Any] = Depends(admin)) -> Dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Aucune clé fournie")
    if changes.get("alert_webhook_url"):
        try:
            validate_webhook_url(changes["alert_webhook_url"])
        except WebhookRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        keys = credentials.update(changes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Écriture du coffre impossible") from exc
    changed = sorted(credentials.CREDENTIALS[k]["env"] for k in changes)
    audit.record("system.keys", actor=user["username"], target="credentials", ip=request_ip(request), details={"changed": changed})
    notify.notify_security("Clés modifiées", level="info",
                           details={"Clés": ", ".join(changed), "Par": user["username"], "Origine": request_ip(request)})
    return {"keys": keys}


@router.post("/settings/keys/test/{service}")
def test_service(service: str, user: Dict[str, Any] = Depends(admin)) -> Dict[str, Any]:
    """Live test of the webhook (one message per channel), of an integrated data source or of a source key."""
    if service == "webhook":
        from app.services.notify import CHANNELS, event_attachment

        results = {
            channel: notify.publish(channel, f"✅ Test du canal #{channel}",
                                    attachment=event_attachment(f"✅ Test du canal #{channel}", "success",
                                                                [{"title": "Rôle du canal", "value": description, "short": False}]),
                                    blocking=True)
            for channel, description in CHANNELS.items()
        }
        ok = all(results.values())
        failed = [c for c, r in results.items() if not r]
        return {"service": service, "ok": ok,
                "message": f"Test envoyé sur les {len(results)} canaux" if ok else f"Échec ou webhook non configuré ({', '.join(failed)})"}
    if service not in CHECKS:
        raise HTTPException(status_code=404, detail=f"Service inconnu : {service}")
    result = check_service(service, get_settings())
    audit.record("system.source_test", actor=user["username"], target=service, outcome="success" if result["ok"] else "failure")
    return {"service": service, **result}


@router.get("/system/settings")
def get_runtime(_user: Dict[str, Any] = Depends(admin)) -> Dict[str, Any]:
    return {"settings": runtime.describe()}


@router.put("/system/settings")
def put_runtime(body: Dict[str, Any], user: Dict[str, Any] = Depends(admin)) -> Dict[str, Any]:
    try:
        return {"settings": runtime.update(body, user["username"])}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/system/health")
def system_health(_user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    from app.territoire import store

    cfg = get_settings()
    return {"sources": health.snapshot(), "data": store.data_freshness(cfg),
            "configured": {"webhook": bool(cfg.alert_webhook_url),
                           "copernicus_cdse": bool(cfg.cdse_client_id and cfg.cdse_client_secret),
                           "protected_planet": bool(cfg.protected_planet_token)},
            "checks": sorted(CHECKS)}


@router.get("/system/supervision")
def technical_supervision(_user: Dict[str, Any] = Depends(admin)) -> Dict[str, Any]:
    from app.services import supervision

    return supervision.snapshot()


@router.get("/system/catalogue")
def catalogue(_user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    from app.services.catalogue import describe

    return {"sources": describe()}


@router.get("/system/ethique")
def ethics(_user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """The usage charter shown on the dashboard (and enforced by the platform)."""
    cfg = get_settings()
    return {
        "title": "Charte d'usage KAP Guyane",
        "principles": [
            {"title": "Un outil de planification, pas de contrôle",
             "text": "La plateforme éclaire l'implantation des équipements et des réseaux. Tout usage fiscal, de contrôle "
                     "de l'urbanisme individuel ou d'expulsion est exclu."},
            {"title": f"Agrégation obligatoire à {cfg.grid_cell_m} m",
             "text": "Toutes les couches sont calculées, stockées et exportées par carreaux de 200 m. Aucune emprise de "
                     "bâtiment n'est conservée : les empreintes sont comptées à la lecture puis oubliées."},
            {"title": "Aucune distinction légal / illégal",
             "text": "Le bâti est mesuré sans qualification juridique. La plateforme ne croise pas le cadastre nominatif "
                     "(fichiers MAJIC exclus)."},
            {"title": "Secret statistique des exports",
             "text": f"Un carreau représentant moins de {cfg.privacy_min_buildings} bâtiments estimés n'est jamais listé "
                     "individuellement dans un export."},
            {"title": "Estimations nommées comme telles",
             "text": "Chaque chiffre modélisé affiche sa méthode, ses hypothèses et ses sources. Un indicateur de croissance "
                     "du bâti n'est pas un contre-recensement : c'est un appui pour demander des vérifications ciblées."},
            {"title": "Traçabilité",
             "text": "Chaque analyse, export et document émis est inscrit au journal d'audit chaîné ; les documents de "
                     "décision sont signés et vérifiables."},
        ],
        "references": [
            "Défenseur des droits, décisions 2023-31 et 2025-102 (article 197 de la loi ELAN)",
            "RGPD : une analyse d'impact (AIPD) est requise avant tout usage opérationnel croisé avec des données personnelles",
        ],
    }
