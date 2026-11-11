"""Security posture: authentication, sessions, CSRF, RBAC, secrets at rest, audit chain, hardening."""

from __future__ import annotations

import datetime
import json
import stat
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core import audit, credentials, identity, vault
from app.core.passwords import hash_password, policy_violations, verify_password
from app.db import db
from tests.conftest import TEST_PASSWORD

PROTECTED = [
    ("GET", "/api/v1/communes"),
    ("GET", "/api/v1/communes/97311"),
    ("GET", "/api/v1/territoire/kpis"),
    ("GET", "/api/v1/grille/97311/couche"),
    ("GET", "/api/v1/grille/97311/recensement"),
    ("GET", "/api/v1/equipements"),
    ("POST", "/api/v1/decision/implantation"),
    ("GET", "/api/v1/scenarios"),
    ("GET", "/api/v1/rapports"),
    ("POST", "/api/v1/analyses"),
    ("GET", "/api/v1/audit"),
    ("GET", "/api/v1/settings/keys"),
    ("GET", "/api/v1/users"),
    ("GET", "/api/v1/system/health"),
]


def _app_client() -> TestClient:
    from server import app

    return TestClient(app)


def test_every_api_endpoint_requires_authentication() -> None:
    client = _app_client()
    for method, path in PROTECTED:
        assert client.request(method, path).status_code == 401, path
    assert client.get("/health").status_code == 200


def test_password_hashing_and_policy() -> None:
    encoded = hash_password("Correct-Horse-9!")
    assert encoded.startswith("scrypt$") and "Correct" not in encoded
    assert verify_password("Correct-Horse-9!", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("x", "garbage")
    assert policy_violations("short", min_length=12)
    assert policy_violations("alllowercaseletters", min_length=12)
    assert any("identifiant" in p for p in policy_violations("Jean.Dupont-2026!", "jean.dupont"))
    assert not policy_violations("Vr4i-M0t-de-Passe!", "alice")


def test_login_is_generic_and_locks_out(make_user: Any) -> None:
    make_user("alice", "analyst")
    client = _app_client()
    unknown = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    wrong = client.post("/api/v1/auth/login", json={"username": "alice", "password": "bad"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]  # no user enumeration
    for _ in range(get_settings().login_max_attempts - 1):
        client.post("/api/v1/auth/login", json={"username": "alice", "password": "bad"})
    locked = client.post("/api/v1/auth/login", json={"username": "alice", "password": TEST_PASSWORD})
    assert locked.status_code == 423  # even the right password is refused while locked
    failures = audit.search(actor="alice", action_prefix="auth.login")
    assert any(e["outcome"] == "failure" for e in failures)


def test_session_cookie_flags_and_logout(make_user: Any) -> None:
    make_user("bob", "viewer")
    client = _app_client()
    response = client.post("/api/v1/auth/login", json={"username": "bob", "password": TEST_PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "kap_session" in cookie
    with db() as conn:  # only the token hash is stored
        stored = conn.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert stored not in response.headers["set-cookie"]
    csrf = response.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_csrf_required_on_state_changes(client_as: Any) -> None:
    client = client_as("analyst")
    token = client.headers.pop("X-CSRF-Token")
    body = {"category": "eau", "lat": 5.49, "lon": -54.02}
    assert client.post("/api/v1/equipements", json=body).status_code == 403
    client.headers["X-CSRF-Token"] = "forged"
    assert client.post("/api/v1/equipements", json=body).status_code == 403
    client.headers["X-CSRF-Token"] = token
    assert client.get("/api/v1/communes").status_code == 200  # reads need no CSRF
    assert client.post("/api/v1/equipements", json=body).status_code == 200


def test_idle_session_expires(make_user: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    make_user("carol", "viewer")
    client = _app_client()
    client.post("/api/v1/auth/login", json={"username": "carol", "password": TEST_PASSWORD})
    old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)).isoformat()
    with db() as conn:
        conn.execute("UPDATE sessions SET last_seen_at = ?", (old,))
    assert client.get("/api/v1/auth/me").status_code == 401


def test_role_based_access_control(client_as: Any) -> None:
    viewer = client_as("viewer")
    assert viewer.get("/api/v1/communes").status_code == 200
    assert viewer.post("/api/v1/analyses", json={"commune": "97311"}).status_code == 403
    assert viewer.post("/api/v1/equipements", json={"category": "eau", "lat": 5.49, "lon": -54.02}).status_code == 403
    assert viewer.get("/api/v1/grille/97311/recensement").status_code == 403  # export reserved to analysts
    assert viewer.get("/api/v1/audit").status_code == 403
    analyst = client_as("analyst")
    assert analyst.get("/api/v1/audit").status_code == 403
    assert analyst.get("/api/v1/settings/keys").status_code == 403
    assert analyst.get("/api/v1/users").status_code == 403
    assert analyst.put("/api/v1/communes/97311/hypothese", json={"year": 2026, "value": 75000}).status_code == 403
    assert analyst.post("/api/v1/rapports/emettre", json={"kind": "diagnostic", "commune": "97311"}).status_code == 403
    supervisor = client_as("supervisor")
    assert supervisor.get("/api/v1/audit").status_code == 200
    assert supervisor.put("/api/v1/settings/keys", json={"alert_webhook_url": "https://hooks.example.org/x"}).status_code == 403
    admin = client_as("admin")
    assert admin.get("/api/v1/users").status_code == 200


def test_bootstrap_admin_must_change_password() -> None:
    password = identity.bootstrap_admin()
    assert password and not policy_violations(password, "admin")
    assert identity.bootstrap_admin() is None  # only once
    client = _app_client()
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": password})
    assert login.status_code == 200 and login.json()["user"]["must_change_password"]
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    assert client.get("/api/v1/communes").status_code == 403  # blocked until changed
    weak = client.post("/api/v1/auth/password", json={"current_password": password, "new_password": "weak"})
    assert weak.status_code == 422
    ok = client.post("/api/v1/auth/password", json={"current_password": password, "new_password": "N0uveau-Secret!"})
    assert ok.status_code == 200
    assert client.get("/api/v1/communes").status_code == 200


def test_admin_user_management_and_reset(client_as: Any) -> None:
    admin = client_as("admin")
    created = admin.post("/api/v1/users", json={"username": "dave", "role": "analyst"}).json()
    temporary = created["temporary_password"]
    assert temporary and created["user"]["must_change_password"]
    assert admin.post("/api/v1/users", json={"username": "dave", "role": "analyst"}).status_code == 422
    assert admin.patch(f"/api/v1/users/{admin.user['id']}", json={"disabled": True}).status_code == 422
    user_id = created["user"]["id"]
    assert admin.patch(f"/api/v1/users/{user_id}", json={"disabled": True}).json()["user"]["disabled"]
    blocked = _app_client().post("/api/v1/auth/login", json={"username": "dave", "password": temporary})
    assert blocked.status_code == 401


def test_secrets_encrypted_at_rest_and_write_only(client_as: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.notify.socket.getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    admin = client_as("admin")
    secret = "https://hooks.example.org/services/T000/B000/SECRET1234567890"
    response = admin.put("/api/v1/settings/keys", json={"alert_webhook_url": secret})
    assert response.status_code == 200 and secret not in response.text
    store = get_settings().keys_dir / credentials.STORE_NAME
    raw = store.read_bytes()
    assert secret.encode() not in raw  # encrypted
    assert stat.S_IMODE(store.stat().st_mode) == 0o600
    assert json.loads(vault.decrypt(raw))["alert_webhook_url"] == secret
    assert get_settings().alert_webhook_url == secret  # applied live
    assert secret not in json.dumps(audit.search(limit=50))  # never audited in clear
    assert response.json()["keys"]["alert_webhook_url"]["hint"] == "••••7890"


def test_legacy_plaintext_store_is_migrated() -> None:
    cfg = get_settings()
    legacy = cfg.keys_dir / credentials.LEGACY_STORE_NAME
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"alert_webhook_url": "https://hooks.example.org/legacy"}))
    credentials.apply_stored_credentials(cfg)
    assert not legacy.exists()
    assert cfg.alert_webhook_url == "https://hooks.example.org/legacy"


def test_webhook_ssrf_guard(client_as: Any) -> None:
    admin = client_as("admin")
    for url in ("http://example.com/hook", "https://127.0.0.1/hook", "https://user:pw@example.com/x", "ftp://x"):
        assert admin.put("/api/v1/settings/keys", json={"alert_webhook_url": url}).status_code == 422, url


def test_pki_private_keys_encrypted() -> None:
    from app.core.pki import ensure_pki, signing_key_pem

    cfg = get_settings()
    ensure_pki(cfg)
    for name in ("key.pem", "rootCA_key.pem"):
        data = (cfg.keys_dir / name).read_bytes()
        assert b"ENCRYPTED PRIVATE KEY" in data
        assert stat.S_IMODE((cfg.keys_dir / name).stat().st_mode) == 0o600
    assert b"BEGIN PRIVATE KEY" in signing_key_pem(cfg)


def test_audit_chain_detects_tampering(client_as: Any) -> None:
    supervisor = client_as("supervisor")
    assert supervisor.get("/api/v1/audit/verify").json()["valid"] is True
    with db() as conn:
        conn.execute("UPDATE audit_log SET actor = 'mallory' WHERE id = 1")
    result = supervisor.get("/api/v1/audit/verify").json()
    assert result["valid"] is False and result["broken_at"] == 1


def test_security_headers(client_as: Any) -> None:
    client = client_as("viewer")
    response = client.get("/api/v1/communes")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_path_parameters_are_validated(client_as: Any) -> None:
    client = client_as("viewer")
    for path in ("/api/v1/communes/..%2F..%2Fkeys", "/api/v1/grille/97311/carreau/..%2Fx", "/api/v1/communes/9731'1"):
        assert client.get(path).status_code in (404, 422), path


def test_api_rate_limit(client_as: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.ratelimit import api_limiter

    client = client_as("viewer")
    monkeypatch.setattr(api_limiter, "limit", 3)
    api_limiter.reset()
    codes = [client.get("/api/v1/communes").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and 429 in codes


def test_untrusted_forwarded_for_is_ignored() -> None:
    from app.core.ratelimit import client_ip

    assert client_ip("203.0.113.9", "1.2.3.4") == "203.0.113.9"  # untrusted peer: header ignored
    assert client_ip("172.18.0.5", "1.2.3.4, 172.18.0.5") == "1.2.3.4"  # docker proxy: trusted


def test_vault_rejects_wrong_master_key(tmp_path: Path) -> None:
    from cryptography.fernet import Fernet

    cfg = get_settings()
    token = vault.encrypt(b"secret", cfg)
    other = cfg.model_copy(update={"master_key": Fernet.generate_key().decode()})
    with pytest.raises(vault.VaultError):
        vault.decrypt(token, other)


def test_master_key_file_is_used_and_never_replaced(tmp_path: Path) -> None:
    """Docker deployment: the key comes from a secret file outside keys/ (hence outside backups)."""
    from cryptography.fernet import Fernet

    from app.core import maintenance

    secret = tmp_path / "secrets" / "master_key"
    secret.parent.mkdir()
    secret.write_bytes(Fernet.generate_key() + b"\n")
    cfg = get_settings().model_copy(update={"master_key_file": str(secret)})
    token = vault.encrypt(b"secret", cfg)
    assert vault.decrypt(token, cfg) == b"secret"
    assert vault.master_key_bytes(cfg) == secret.read_bytes().strip()
    assert not (cfg.keys_dir / vault.MASTER_KEY_FILE).exists()  # nothing generated next to the encrypted data
    archive, _digest = maintenance.create_backup(cfg)
    import tarfile

    with tarfile.open(archive) as tar:
        assert not any(name.endswith("master.key") or name.endswith("master_key") for name in tar.getnames())
    # A missing / corrupt secret must fail loudly, never silently generate a different key.
    missing = cfg.model_copy(update={"master_key_file": str(tmp_path / "absent")})
    with pytest.raises(vault.VaultError):
        vault.encrypt(b"x", missing)
