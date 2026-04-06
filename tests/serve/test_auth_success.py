"""AQ-14: Serve API authorized success path test."""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from sable.serve.app import create_app
from sable.roster.models import Account
from tests.serve.conftest import make_sqlite, PULSE_SCHEMA, META_SCHEMA


def _cfg_with_token(token: str):
    def _get(key, default=None):
        if key == "serve":
            return {"tokens": {"testclient": token}, "rate_limit_rpm": 60}
        return default
    return _get


def test_authorized_performance_returns_200(monkeypatch):
    """Valid token + valid org returns 200 with performance data."""
    monkeypatch.setattr("sable.serve.auth.cfg.get", _cfg_with_token("valid-tok"))

    app = create_app()
    pulse = make_sqlite(PULSE_SCHEMA)
    meta = make_sqlite(META_SCHEMA)
    accounts = [Account(handle="@test", org="testorg")]

    with patch("sable.serve.routes.pulse.get_pulse_db", return_value=pulse), \
         patch("sable.serve.routes.pulse.get_meta_db", return_value=meta), \
         patch("sable.serve.routes.pulse.list_accounts", return_value=accounts):
        client = TestClient(app)
        resp = client.get(
            "/api/pulse/performance/testorg",
            headers={"Authorization": "Bearer valid-tok"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "total_posts" in data


def test_authorized_posting_log_returns_200(monkeypatch):
    """Valid token returns 200 on posting-log endpoint."""
    monkeypatch.setattr("sable.serve.auth.cfg.get", _cfg_with_token("valid-tok"))

    app = create_app()
    pulse = make_sqlite(PULSE_SCHEMA)
    meta = make_sqlite(META_SCHEMA)
    accounts = [Account(handle="@test", org="testorg")]

    with patch("sable.serve.routes.pulse.get_pulse_db", return_value=pulse), \
         patch("sable.serve.routes.pulse.get_meta_db", return_value=meta), \
         patch("sable.serve.routes.pulse.list_accounts", return_value=accounts):
        client = TestClient(app)
        resp = client.get(
            "/api/pulse/posting-log/testorg",
            headers={"Authorization": "Bearer valid-tok"},
        )

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
