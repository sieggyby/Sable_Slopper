"""Tests for pulse API routes."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sable.serve.app import create_app
from fastapi import Request

from sable.serve.auth import verify_token
from sable.roster.models import Account
from sable.vault.permissions import ClientIdentity, Role
from tests.serve.conftest import make_sqlite, PULSE_SCHEMA, META_SCHEMA


def _bypass_auth(request: Request):
    request.state.identity = ClientIdentity(name="test", role=Role.admin)
    request.state.client_name = "test"


_ACCOUNTS = [Account(handle="@test_acct", org="testorg")]


def _make_client(pulse_db, meta_db=None, accounts=None):
    if meta_db is None:
        meta_db = make_sqlite(META_SCHEMA)
    app = create_app()
    app.dependency_overrides[verify_token] = _bypass_auth
    patches = [
        patch("sable.serve.routes.pulse.get_pulse_db", return_value=pulse_db),
        patch("sable.serve.routes.pulse.get_meta_db", return_value=meta_db),
        patch("sable.serve.routes.pulse.list_accounts", return_value=accounts if accounts is not None else _ACCOUNTS),
    ]
    for p in patches:
        p.start()
    client = TestClient(app)
    client._patches = patches  # type: ignore[attr-defined]
    return client


def _stop(client):
    for p in client._patches:  # type: ignore[attr-defined]
        p.stop()


def test_performance_empty():
    """Empty pulse DB → zeroed metrics."""
    pulse = make_sqlite(PULSE_SCHEMA)
    c = _make_client(pulse)
    try:
        resp = c.get("/api/pulse/performance/testorg")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_posts"] == 0
        assert data["sable_posts"] == 0
        assert data["organic_posts"] == 0
    finally:
        _stop(c)


def test_performance_with_posts():
    """Posts with snapshots → correct aggregation."""
    pulse = make_sqlite(PULSE_SCHEMA)
    pulse.execute(
        "INSERT INTO posts (id, account_handle, posted_at, sable_content_type) VALUES (?, ?, ?, ?)",
        ("p1", "@test_acct", "2026-04-01 12:00:00", "meme"),
    )
    pulse.execute(
        "INSERT INTO snapshots (post_id, likes, retweets, replies, views, bookmarks, quotes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("p1", 100, 20, 5, 1000, 10, 3),
    )
    pulse.execute(
        "INSERT INTO posts (id, account_handle, posted_at) VALUES (?, ?, ?)",
        ("p2", "@test_acct", "2026-04-01 14:00:00"),
    )
    pulse.execute(
        "INSERT INTO snapshots (post_id, likes, retweets, replies, views, bookmarks, quotes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("p2", 50, 10, 2, 500, 5, 1),
    )
    pulse.commit()

    c = _make_client(pulse)
    try:
        resp = c.get("/api/pulse/performance/testorg")
        data = resp.json()
        assert data["total_posts"] == 2
        assert data["sable_posts"] == 1
        assert data["organic_posts"] == 1
        assert data["sable_avg_engagement"] > 0
        assert len(data["by_format"]) == 1
        assert data["by_format"][0]["format"] == "meme"
        # AQ-11: sample_sizes metadata included for trustworthiness
        assert "sample_sizes" in data
        assert data["sample_sizes"]["total_posts"] == 2
        assert data["sample_sizes"]["sable_posts"] == 1
    finally:
        _stop(c)


def test_performance_no_accounts():
    """No accounts for org → error response."""
    pulse = make_sqlite(PULSE_SCHEMA)
    c = _make_client(pulse, accounts=[])
    try:
        resp = c.get("/api/pulse/performance/testorg")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] == "No accounts found for org"
        assert data["org"] == "testorg"
    finally:
        _stop(c)


def test_posting_log():
    """Posting log returns raw rows."""
    pulse = make_sqlite(PULSE_SCHEMA)
    pulse.execute(
        "INSERT INTO posts (id, account_handle, posted_at, sable_content_type) VALUES (?, ?, ?, ?)",
        ("p1", "@test_acct", "2026-04-01 12:00:00", "clip"),
    )
    pulse.execute(
        "INSERT INTO snapshots (post_id, likes, retweets, replies, views, bookmarks, quotes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("p1", 50, 5, 2, 200, 3, 1),
    )
    pulse.commit()

    c = _make_client(pulse)
    try:
        resp = c.get("/api/pulse/posting-log/testorg")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "p1"
        assert data[0]["likes"] == 50
    finally:
        _stop(c)


def test_posting_log_no_accounts():
    """No accounts → empty list."""
    pulse = make_sqlite(PULSE_SCHEMA)
    c = _make_client(pulse, accounts=[])
    try:
        resp = c.get("/api/pulse/posting-log/testorg")
        assert resp.json() == []
    finally:
        _stop(c)
