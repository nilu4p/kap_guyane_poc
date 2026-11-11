"""Outbound notifications (Slack / Mattermost compatible webhooks), routed by channel.

Channels
--------
``veille``     territorial watch: strong built-up growth far from facilities, saturation
``analyses``   satellite analyses finished or failed (with their quality figures)
``donnees``    open-data synchronisations, data-source outages and recoveries
``decisions``  scenarios validated, signed decision documents issued
``securite``   admin creation, break-glass, factory reset / restore, audit-chain integrity

Routing: if ``ALERT_WEBHOOK_URL`` contains ``{channel}`` (or ``__CHANNEL__``, handy in
docker-compose defaults where braces are not allowed) it is substituted (e.g. the PoC
sink ``http://notif-sink:8090/hooks/{channel}``); otherwise the single URL is used and
the payload carries ``"channel": "kap-<name>"``.

SSRF guard: https only, public addresses only, no redirects. Hosts listed in
``WEBHOOK_ALLOWED_HOSTS`` (the local sink) are trusted explicitly.
Anti-flood: identical keys are throttled (``cooldown`` seconds).
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.config import Settings, get_settings
from app.core import shared
from app.sources import health

logger = logging.getLogger(__name__)

CHANNELS: Dict[str, str] = {
    "veille": "Veille territoriale : croissance du bâti loin des équipements, saturations",
    "analyses": "Analyses satellitaires terminées ou en échec",
    "donnees": "Synchronisation des données ouvertes, santé des sources",
    "decisions": "Scénarios validés, documents de décision signés",
    "securite": "Événements de sécurité de la plateforme",
}
LEVEL_COLORS = {"info": "#38bdf8", "success": "#22c55e", "warning": "#f59e0b", "danger": "#ef4444"}


class WebhookRejected(ValueError):
    """The webhook URL fails the SSRF policy."""


# --------------------------------------------------------------------------- transport


def validate_webhook_url(url: str, settings: Optional[Settings] = None) -> str:
    cfg = settings or get_settings()
    candidate = channel_url(url.strip(), "veille")
    parsed = urlparse(candidate)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise WebhookRejected("URL de webhook invalide")
    trusted = cfg.allow_insecure_webhooks or parsed.hostname in cfg.webhook_allowed_hosts
    if parsed.scheme != "https" and not trusted:
        raise WebhookRejected("Le webhook doit utiliser HTTPS")
    if parsed.username or parsed.password:
        raise WebhookRejected("Identifiants interdits dans l'URL")
    if trusted:
        return url.strip()
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise WebhookRejected("Nom d'hôte du webhook introuvable") from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise WebhookRejected("Le webhook pointe vers une adresse interne (SSRF bloqué)")
    return url.strip()


def channel_url(base: str, channel: str) -> str:
    return base.replace("{channel}", channel).replace("__CHANNEL__", channel)


def _post(url: str, payload: Dict[str, Any], cfg: Settings) -> bool:
    try:
        validate_webhook_url(url, cfg)
        response = httpx.post(url, json=payload, timeout=cfg.http_timeout, follow_redirects=False)
        ok = response.status_code < 400
        health.record("webhook", ok, "" if ok else f"HTTP {response.status_code}")
        return ok
    except Exception as exc:
        health.record("webhook", False, type(exc).__name__)
        logger.warning("Webhook notification failed: %s", type(exc).__name__)
        return False


def _throttled(key: Optional[str], cooldown: float) -> bool:
    """Anti-repeat shared by every process (API, workers): first sender in the window wins."""
    if not key or cooldown <= 0:
        return False
    try:
        return not shared.first_in(f"notify:{key}", cooldown)
    except Exception:  # Redis unavailable: better a duplicate than a lost message
        return False


def publish(
    channel: str,
    text: str,
    *,
    attachment: Optional[Dict[str, Any]] = None,
    key: Optional[str] = None,
    cooldown: float = 0,
    settings: Optional[Settings] = None,
    blocking: bool = False,
) -> bool:
    """Send one message to a channel. Returns False if not configured or throttled."""
    cfg = settings or get_settings()
    if not cfg.alert_webhook_url or channel not in CHANNELS:
        return False
    if _throttled(key, cooldown):
        return False
    payload: Dict[str, Any] = {
        "channel": f"kap-{channel}",
        "username": "KAP Guyane",
        "icon_emoji": ":satellite:",
        "text": text,
    }
    if attachment:
        payload["attachments"] = [attachment]
    url = channel_url(cfg.alert_webhook_url, channel)
    if blocking:
        return _post(url, payload, cfg)
    if cfg.background_mode == "workers" and _enqueue(url, payload):
        return True
    _spawn(_post, url, payload, cfg)
    return True


def _enqueue(url: str, payload: Dict[str, Any]) -> bool:
    """Durable delivery through the ``notify`` queue (retries with backoff); False if the broker is down."""
    try:
        from app.tasks import notify as notify_task

        notify_task.apply_async(args=[url, payload], queue="notify")
        return True
    except Exception as exc:
        logger.warning("Notification queue unavailable (%s): direct delivery", type(exc).__name__)
        return False


def _spawn(target: Any, *args: Any) -> None:
    """Fire-and-forget delivery (isolated so tests can run it inline)."""
    threading.Thread(target=target, args=args, daemon=True).start()


# --------------------------------------------------------------------------- formatting


def _field(title: str, value: Any, short: bool = True) -> Optional[Dict[str, Any]]:
    if value is None or value == "" or value == []:
        return None
    return {"title": title, "value": str(value), "short": short}


def _links(cfg: Settings, view: str = "", label: str = "") -> List[Dict[str, str]]:
    base = cfg.public_url.rstrip("/")
    actions = []
    if view:
        actions.append({"type": "button", "text": label or "Ouvrir", "url": f"{base}/#/{view}"})
    actions.append({"type": "button", "text": "Tableau de bord", "url": f"{base}/#/territoire"})
    return actions


def event_attachment(title: str, level: str, fields: List[Optional[Dict[str, Any]]], *,
                     view: str = "", label: str = "", settings: Optional[Settings] = None) -> Dict[str, Any]:
    cfg = settings or get_settings()
    return {
        "fallback": title,
        "color": LEVEL_COLORS.get(level, LEVEL_COLORS["info"]),
        "title": title,
        "fields": [f for f in fields if f],
        "footer": "KAP Guyane · aide à la décision territoriale",
        "actions": _links(cfg, view, label),
    }


def notify_event(channel: str, title: str, *, level: str = "info", details: Optional[Dict[str, Any]] = None,
                 view: str = "", label: str = "", key: Optional[str] = None, cooldown: float = 0,
                 settings: Optional[Settings] = None, blocking: bool = False) -> bool:
    fields = [_field(k, v, short=len(str(v)) < 40) for k, v in (details or {}).items()]
    return publish(channel, title, attachment=event_attachment(title, level, fields, view=view, label=label, settings=settings),
                   key=key, cooldown=cooldown, settings=settings, blocking=blocking)


def notify_source_health(source: str, status: str, error: str = "", settings: Optional[Settings] = None) -> bool:
    down = status == "down"
    title = f"Source {'indisponible' if down else 'rétablie'} : {source}"
    return notify_event("donnees", title, level="danger" if down else "success",
                        details={"Source": source, "Erreur": error or None}, key=f"health:{source}:{status}",
                        cooldown=3600, settings=settings)


def notify_security(title: str, *, level: str = "warning", details: Optional[Dict[str, Any]] = None,
                    settings: Optional[Settings] = None, blocking: bool = False, key: Optional[str] = None,
                    cooldown: float = 0) -> bool:
    return notify_event("securite", f"🔐 {title}", level=level, details=details, view="audit", label="Journal d'audit",
                        key=key, cooldown=cooldown, settings=settings, blocking=blocking)
