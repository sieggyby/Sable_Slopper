"""Tests for app factory and health endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sable.serve.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def test_health_no_auth(client):
    """Health endpoint requires no auth and returns checks."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "checks" in data


def test_app_has_routes(app):
    """App registers vault, pulse, meta routers."""
    paths = [r.path for r in app.routes]
    assert "/health" in paths
    # Check prefixed routes exist
    route_paths = " ".join(paths)
    assert "/api/vault/" in route_paths or any("/api/vault" in p for p in paths)
    assert "/api/pulse/" in route_paths or any("/api/pulse" in p for p in paths)
    assert "/api/meta/" in route_paths or any("/api/meta" in p for p in paths)


def test_protected_route_requires_auth(client):
    """API routes return 401 without token."""
    resp = client.get("/api/pulse/performance/testorg")
    assert resp.status_code == 401


def test_protected_route_rejects_bad_token(client, monkeypatch):
    """API routes return 403 with wrong token."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"token": "correct-token"} if key == "serve" else default,
    )
    resp = client.get(
        "/api/pulse/performance/testorg",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────
# App-level rate-limit integration tests
# ─────────────────────────────────────────────────────────────────────

def _cfg_with_tokens(tokens: dict, rpm: int = 3):
    """Return a serve config getter stub with named tokens."""
    def _get(key, default=None):
        if key == "serve":
            return {"tokens": tokens, "rate_limit_rpm": rpm}
        return default
    return _get


def test_rate_limit_per_client_independent(monkeypatch):
    """Two named bearer tokens hitting the same endpoint have independent buckets."""
    tokens = {"alice": "tok_alice", "bob": "tok_bob"}
    monkeypatch.setattr("sable.serve.auth.cfg.get", _cfg_with_tokens(tokens, rpm=2))

    app = create_app()
    client = TestClient(app)
    alice_h = {"Authorization": "Bearer tok_alice"}
    bob_h = {"Authorization": "Bearer tok_bob"}

    # Fill alice's bucket (2 rpm)
    for _ in range(2):
        client.get("/api/pulse/performance/testorg", headers=alice_h)

    # Alice is throttled
    resp = client.get("/api/pulse/performance/testorg", headers=alice_h)
    assert resp.status_code == 429

    # Bob is unaffected on the same route
    resp = client.get("/api/pulse/performance/testorg", headers=bob_h)
    assert resp.status_code != 429


def test_anonymous_traffic_does_not_consume_auth_budget(monkeypatch):
    """Anonymous requests do not eat into an authenticated client's rate-limit budget."""
    tokens = {"alice": "tok_alice"}
    monkeypatch.setattr("sable.serve.auth.cfg.get", _cfg_with_tokens(tokens, rpm=2))

    app = create_app()
    client = TestClient(app)

    # Fill anonymous bucket (no auth header)
    for _ in range(2):
        client.get("/api/pulse/performance/testorg")
    # Anonymous is throttled (or gets 401 — either way, not 200)
    resp = client.get("/api/pulse/performance/testorg")
    assert resp.status_code in (401, 429)

    # Authenticated client still has capacity
    resp = client.get(
        "/api/pulse/performance/testorg",
        headers={"Authorization": "Bearer tok_alice"},
    )
    assert resp.status_code != 429
