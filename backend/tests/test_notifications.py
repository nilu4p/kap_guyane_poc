"""Notifications: channel routing, sources, security, anti-flood, test button."""

from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pytest

from app.config import get_settings
from app.services import notify, scheduler


@pytest.fixture()
def captured(monkeypatch: pytest.MonkeyPatch) -> List[Dict[str, Any]]:
    """Capture webhook calls synchronously."""
    calls: List[Dict[str, Any]] = []
    cfg = get_settings()
    monkeypatch.setattr(cfg, "alert_webhook_url", "http://notif-sink:8090/hooks/{channel}")
    monkeypatch.setattr(cfg, "webhook_allowed_hosts", ["notif-sink"])

    def fake_post(url: str, json: Dict[str, Any], **_kw: Any) -> httpx.Response:
        calls.append({"url": url, "payload": json})
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    monkeypatch.setattr(notify, "_spawn", lambda target, *args: target(*args))
    return calls


def test_routing_per_channel_and_single_url(captured: List[Dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    assert notify.notify_event("analyses", "Analyse terminée", details={"Commune": "Saint-Laurent"})
    assert captured[-1]["url"].endswith("/hooks/analyses")
    card = captured[-1]["payload"]["attachments"][0]
    assert card["title"] == "Analyse terminée" and card["fields"][0]["value"] == "Saint-Laurent"
    monkeypatch.setattr(get_settings(), "alert_webhook_url", "http://notif-sink:8090/hooks/single")
    notify.publish("veille", "x")
    assert captured[-1]["url"].endswith("/hooks/single") and captured[-1]["payload"]["channel"] == "kap-veille"
    assert notify.publish("inconnu", "x") is False


def test_anti_flood_key(captured: List[Dict[str, Any]]) -> None:
    for _ in range(3):
        notify.notify_event("veille", "Même alerte", key="same", cooldown=3600)
    assert sum(c["payload"]["text"] == "Même alerte" for c in captured) == 1


def test_source_outage_and_recovery_are_notified_once(captured: List[Dict[str, Any]]) -> None:
    from app.sources import health

    health.record("insee_melodi", True)
    scheduler.watch_sources()
    for _ in range(3):
        health.record("insee_melodi", False, "HTTP 503")
    assert scheduler.watch_sources() == 1
    assert scheduler.watch_sources() == 0  # still down: no repeat
    health.record("insee_melodi", True)
    assert scheduler.watch_sources() == 1
    titles = [c["payload"]["text"] for c in captured]
    assert titles == ["Source indisponible : insee_melodi", "Source rétablie : insee_melodi"]
    assert all(c["url"].endswith("/hooks/donnees") for c in captured)


def test_lockout_and_audit_tamper_go_to_securite(captured: List[Dict[str, Any]], make_user: Any) -> None:
    from app.core import identity
    from app.db import db

    make_user("bob", "analyst")
    for _ in range(get_settings().login_max_attempts):
        with pytest.raises(identity.AuthError):
            identity.login("bob", "bad", ip="203.0.113.7", user_agent="t")
    lock = [c for c in captured if "verrouillé" in c["payload"]["text"]]
    assert len(lock) == 1 and lock[0]["url"].endswith("/hooks/securite")
    assert scheduler.check_audit_chain() is True
    with db() as conn:
        conn.execute("UPDATE audit_log SET actor = 'mallory' WHERE id = 1")
    assert scheduler.check_audit_chain() is False
    assert "ALTÉRÉ" in captured[-1]["payload"]["text"]
    scheduler.check_audit_chain()
    assert sum("ALTÉRÉ" in c["payload"]["text"] for c in captured) == 1  # throttled


def test_webhook_test_button_hits_every_channel(captured: List[Dict[str, Any]], client_as: Any) -> None:
    result = client_as("admin").post("/api/v1/settings/keys/test/webhook").json()
    assert result["ok"] is True
    assert sorted(c["url"].rsplit("/", 1)[-1] for c in captured if "Test du canal" in c["payload"]["text"]) == sorted(notify.CHANNELS)
