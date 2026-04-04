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
    """Health endpoint requires no auth."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


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
