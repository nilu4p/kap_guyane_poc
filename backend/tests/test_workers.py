"""Scalable deployment: shared state in Redis, Celery tasks, workers mode of the API."""

from __future__ import annotations

from typing import Any, Dict, List

import fakeredis
import pytest

from app.config import get_settings
from app.core import shared


@pytest.fixture()
def redis_mode(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Every process of the deployment talks to the same (fake) Redis server."""
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(get_settings(), "redis_url", "redis://redis:6379/0")
    monkeypatch.setattr(shared, "store", lambda settings=None: client)
    return client


@pytest.fixture()
def eager_celery(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.worker import celery_app

    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", True)


def test_health_and_throttle_are_shared(redis_mode: Any) -> None:
    from app.sources import health

    health.record("insee_melodi", False, "HTTP 503")
    health.record("insee_melodi", False, "HTTP 503")
    assert health.snapshot()["insee_melodi"]["consecutive_failures"] == 2
    assert shared.first_in("notify:x", 60) and not shared.first_in("notify:x", 60)


def test_redis_password_comes_from_the_secret_file(tmp_path: Any) -> None:
    secret = tmp_path / "redis_password"
    secret.write_text("s3cr3t/+\n")
    cfg = get_settings().model_copy(update={"redis_url": "redis://redis:6379/0", "redis_password_file": str(secret)})
    assert shared.redis_url(cfg) == "redis://:s3cr3t%2F%2B@redis:6379/0"
    from app.db import database_dsn

    db_secret = tmp_path / "pg"
    db_secret.write_text("pa ss\n")
    pg = get_settings().model_copy(update={"database_url": "postgresql://kap@postgres:5432/kap",
                                           "database_password_file": str(db_secret)})
    assert database_dsn(pg) == "postgresql://kap:pa%20ss@postgres:5432/kap"


def test_workers_mode_api_queues_analyses(client_as: Any, redis_mode: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import tasks
    from app.territoire import store

    store.ensure_communes()
    monkeypatch.setattr(get_settings(), "background_mode", "workers")
    sent: List[Any] = []

    monkeypatch.setattr(tasks.analysis, "apply_async", lambda args, queue: sent.append((args, queue)))
    analyst = client_as("analyst")
    first = analyst.post("/api/v1/analyses", json={"commune": "97311"}).json()["job"]
    assert sent == [([first["id"]], "analysis")] and first["status"] == "queued"
    # A second request while the first is pending returns the same job (no duplicate work).
    again = analyst.post("/api/v1/analyses", json={"commune": "97311"}).json()["job"]
    assert again["id"] == first["id"] and len(sent) == 1


def test_analysis_task_runs_the_job(eager_celery: None, redis_mode: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import tasks
    from app.analyse import jobs
    from app.territoire import store

    store.ensure_communes()
    calls: List[Any] = []
    monkeypatch.setattr(jobs, "prepare_commune", lambda code, params, cfg, progress: calls.append(code) or {"ok": True})
    job = jobs.create("commune", "97311", {}, "analyste")
    tasks.analysis.delay(job["id"])
    assert calls == ["97311"] and jobs.get(job["id"])["status"] == "done"


def test_hourly_tick_checks_the_audit_chain(eager_celery: None, redis_mode: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    checked: List[int] = []
    monkeypatch.setattr("app.services.scheduler.check_audit_chain", lambda cfg=None: checked.append(1) or True)
    monkeypatch.setattr("app.services.scheduler.refresh_data_if_due", lambda cfg=None: None)
    from app import tasks

    tasks.hourly.delay()
    assert checked == [1]


def test_notifications_go_through_the_retry_queue(redis_mode: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.notify as notify_module

    cfg = get_settings()
    monkeypatch.setattr(cfg, "background_mode", "workers")
    monkeypatch.setattr(cfg, "alert_webhook_url", "https://hooks.example.org/{channel}")
    queued: List[Dict[str, Any]] = []
    from app import tasks

    monkeypatch.setattr(tasks.notify, "apply_async", lambda args, queue: queued.append({"url": args[0], "queue": queue}))
    assert notify_module.publish("veille", "test")
    assert queued == [{"url": "https://hooks.example.org/veille", "queue": "notify"}]


def test_readiness_probe(client_as: Any) -> None:
    from fastapi.testclient import TestClient

    from server import app

    body = TestClient(app).get("/health/ready").json()
    assert body == {"status": "ok", "database": True, "shared_state": True}


def test_login_limits_are_shared_between_api_processes(redis_mode: Any) -> None:
    from app.core.ratelimit import SlidingWindowLimiter

    process_a, process_b = SlidingWindowLimiter(3, name="login"), SlidingWindowLimiter(3, name="login")
    assert process_a.hit("ip:1.2.3.4") and process_b.hit("ip:1.2.3.4") and process_a.hit("ip:1.2.3.4")
    assert not process_b.hit("ip:1.2.3.4")
