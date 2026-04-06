"""Tests for cost forecast API routes."""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from sable.serve.app import create_app
from sable.serve.auth import verify_token
from sable.vault.permissions import ClientIdentity, Role


COST_SCHEMA = """
CREATE TABLE cost_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL,
    job_id TEXT,
    call_type TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL NOT NULL,
    call_status TEXT DEFAULT 'success',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE orgs (
    org_id TEXT PRIMARY KEY,
    display_name TEXT,
    discord_server_id TEXT,
    twitter_handle TEXT,
    config_json TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


def _make_cost_db(schema: str = COST_SCHEMA) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(schema)
    return conn


def _bypass_auth_admin(request: Request):
    request.state.identity = ClientIdentity(name="test", role=Role.admin)
    request.state.client_name = "test"


def _bypass_auth_operator(request: Request):
    """Operator with access only to 'allowed_org'."""
    request.state.identity = ClientIdentity(
        name="operator", role=Role.operator, allowed_orgs=("allowed_org",),
    )
    request.state.client_name = "operator"


def _get_weekly_spend_stub(conn, org_id):
    """Simplified weekly spend: sum all cost_events for org."""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_events WHERE org_id = ?",
        (org_id,),
    ).fetchone()
    return float(row[0])


def _get_org_cost_cap_stub(conn, org_id):
    return 5.00


def _make_client(cost_db: sqlite3.Connection, auth_fn=_bypass_auth_admin):
    app = create_app()
    app.dependency_overrides[verify_token] = auth_fn
    patches = [
        patch("sable.platform.db.get_db", return_value=cost_db),
        patch("sable.platform.cost.get_weekly_spend", side_effect=_get_weekly_spend_stub),
        patch("sable.platform.cost.get_org_cost_cap", side_effect=_get_org_cost_cap_stub),
    ]
    for p in patches:
        p.start()
    client = TestClient(app)
    client._patches = patches  # type: ignore[attr-defined]
    return client


def _stop(client):
    for p in client._patches:  # type: ignore[attr-defined]
        p.stop()


class TestCostForecast:
    def test_empty_returns_zeros(self):
        db = _make_cost_db()
        c = _make_client(db)
        try:
            resp = c.get("/api/v1/cost/org/testorg/cost-forecast")
            assert resp.status_code == 200
            data = resp.json()
            assert data["weekly_estimated_usd"] == 0.0
            assert data["monthly_estimated_usd"] == 0.0
            assert data["last_7d_actual_usd"] == 0.0
            assert data["budget_remaining_usd"] == 5.0
            assert data["top_cost_drivers"] == []
        finally:
            _stop(c)

    def test_with_cost_data(self):
        db = _make_cost_db()
        db.execute(
            "INSERT INTO cost_events (org_id, call_type, model, cost_usd) VALUES (?, ?, ?, ?)",
            ("testorg", "socialdata_meta_scan", "socialdata", 2.50),
        )
        db.execute(
            "INSERT INTO cost_events (org_id, call_type, model, cost_usd) VALUES (?, ?, ?, ?)",
            ("testorg", "claude_advise", "claude-sonnet-4-6", 1.00),
        )
        db.commit()

        c = _make_client(db)
        try:
            resp = c.get("/api/v1/cost/org/testorg/cost-forecast")
            assert resp.status_code == 200
            data = resp.json()
            assert data["last_7d_actual_usd"] == 3.50
            assert data["weekly_estimated_usd"] == 3.50
            assert data["monthly_estimated_usd"] == round(3.50 * 4.33, 2)
            assert data["budget_remaining_usd"] == 1.50  # 5.0 - 3.5
            assert len(data["top_cost_drivers"]) == 2
            # Sorted by cost descending
            assert data["top_cost_drivers"][0]["call_type"] == "socialdata_meta_scan"
            assert data["top_cost_drivers"][0]["cost_usd"] == 2.50
        finally:
            _stop(c)

    def test_org_access_denied(self):
        db = _make_cost_db()
        c = _make_client(db, auth_fn=_bypass_auth_operator)
        try:
            resp = c.get("/api/v1/cost/org/forbidden_org/cost-forecast")
            assert resp.status_code == 403
        finally:
            _stop(c)

    def test_top_drivers_ordering(self):
        db = _make_cost_db()
        for ct, cost in [("a_type", 0.50), ("b_type", 2.00), ("c_type", 1.00)]:
            db.execute(
                "INSERT INTO cost_events (org_id, call_type, cost_usd) VALUES (?, ?, ?)",
                ("testorg", ct, cost),
            )
        db.commit()

        c = _make_client(db)
        try:
            resp = c.get("/api/v1/cost/org/testorg/cost-forecast")
            data = resp.json()
            drivers = data["top_cost_drivers"]
            assert len(drivers) == 3
            assert drivers[0]["call_type"] == "b_type"
            assert drivers[1]["call_type"] == "c_type"
            assert drivers[2]["call_type"] == "a_type"
        finally:
            _stop(c)
