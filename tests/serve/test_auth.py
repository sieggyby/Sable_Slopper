"""Tests for token authentication."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sable.serve.auth import verify_token


@pytest.fixture
def app():
    app = FastAPI()

    @app.get("/protected", dependencies=[pytest.importorskip("fastapi").Depends(verify_token)])
    def protected():
        return {"ok": True}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_missing_auth_header(client):
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert "Missing" in resp.json()["detail"]


def test_malformed_auth_header(client):
    resp = client.get("/protected", headers={"Authorization": "Basic abc"})
    assert resp.status_code == 401


def test_token_not_configured(client, monkeypatch):
    """serve.token not set in config → 500."""
    monkeypatch.setattr("sable.serve.auth.cfg.get", lambda key, default=None: default)
    resp = client.get("/protected", headers={"Authorization": "Bearer sometoken"})
    assert resp.status_code == 500
    assert "not configured" in resp.json()["detail"]


def test_wrong_token(client, monkeypatch):
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"token": "correct"} if key == "serve" else default,
    )
    resp = client.get("/protected", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 403


def test_correct_token(client, monkeypatch):
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"token": "correct"} if key == "serve" else default,
    )
    resp = client.get("/protected", headers={"Authorization": "Bearer correct"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_timing_safe_comparison(client, monkeypatch):
    """Token comparison uses hmac.compare_digest (constant-time)."""
    from unittest.mock import patch as _patch
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"token": "correct"} if key == "serve" else default,
    )
    with _patch("sable.serve.auth.hmac.compare_digest", return_value=True) as mock_cmp:
        resp = client.get("/protected", headers={"Authorization": "Bearer correct"})
    assert resp.status_code == 200
    mock_cmp.assert_called_once()
