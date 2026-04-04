"""Tests for meta API routes."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sable.serve.app import create_app
from sable.serve.auth import verify_token
from tests.serve.conftest import make_sqlite, META_SCHEMA


def _bypass_auth():
    pass


def _make_client(meta_db):
    app = create_app()
    app.dependency_overrides[verify_token] = _bypass_auth
    p = patch("sable.serve.routes.meta.get_meta_db", return_value=meta_db)
    p.start()
    client = TestClient(app)
    client._meta_patch = p  # type: ignore[attr-defined]
    return client


def _stop(client):
    client._meta_patch.stop()  # type: ignore[attr-defined]


def test_topics_empty():
    meta = make_sqlite(META_SCHEMA)
    c = _make_client(meta)
    try:
        resp = c.get("/api/meta/topics/testorg")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        _stop(c)


def test_topics_with_data():
    meta = make_sqlite(META_SCHEMA)
    meta.execute(
        "INSERT INTO scan_runs (org, completed_at, mode) VALUES (?, datetime('now'), 'full')",
        ("testorg",),
    )
    scan_id = meta.execute("SELECT last_insert_rowid()").fetchone()[0]
    meta.execute(
        "INSERT INTO topic_signals (org, scan_id, term, mention_count, unique_authors, avg_lift, acceleration) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("testorg", scan_id, "ZK proofs", 15, 5, 3.2, 2.0),
    )
    meta.execute(
        "INSERT INTO topic_signals (org, scan_id, term, mention_count, unique_authors, avg_lift, acceleration) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("testorg", scan_id, "airdrops", 3, 2, 1.1, 0.3),
    )
    meta.commit()

    c = _make_client(meta)
    try:
        resp = c.get("/api/meta/topics/testorg")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["topic"] == "ZK proofs"
        assert data[0]["confidence"] == "high"
        assert data[0]["trend_status"] == "rising"
        assert data[1]["topic"] == "airdrops"
        assert data[1]["trend_status"] == "declining"
    finally:
        _stop(c)


def test_baselines_empty():
    meta = make_sqlite(META_SCHEMA)
    c = _make_client(meta)
    try:
        resp = c.get("/api/meta/baselines/testorg")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        _stop(c)


def test_baselines_with_data():
    meta = make_sqlite(META_SCHEMA)
    meta.execute(
        "INSERT INTO format_baselines (org, format_bucket, period_days, avg_total_lift, sample_count, unique_authors) VALUES (?, ?, ?, ?, ?, ?)",
        ("testorg", "meme", 30, 2.1, 20, 8),
    )
    meta.execute(
        "INSERT INTO format_baselines (org, format_bucket, period_days, avg_total_lift, sample_count, unique_authors) VALUES (?, ?, ?, ?, ?, ?)",
        ("testorg", "thread", 30, 0.5, 10, 4),
    )
    meta.commit()

    c = _make_client(meta)
    try:
        resp = c.get("/api/meta/baselines/testorg")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["format"] == "meme"
        assert data[0]["signal"] == "DOUBLE_DOWN"
        assert data[1]["format"] == "thread"
        assert data[1]["signal"] == "EXECUTION_GAP"
    finally:
        _stop(c)


def test_baselines_fallback_to_7d():
    """No 30d baselines → falls back to 7d."""
    meta = make_sqlite(META_SCHEMA)
    meta.execute(
        "INSERT INTO format_baselines (org, format_bucket, period_days, avg_total_lift, sample_count, unique_authors) VALUES (?, ?, ?, ?, ?, ?)",
        ("testorg", "clip", 7, 1.8, 5, 3),
    )
    meta.commit()

    c = _make_client(meta)
    try:
        resp = c.get("/api/meta/baselines/testorg")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["format"] == "clip"
    finally:
        _stop(c)


def test_watchlist_empty():
    meta = make_sqlite(META_SCHEMA)
    c = _make_client(meta)
    try:
        resp = c.get("/api/meta/watchlist/testorg")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_authors"] == 0
        assert data["coverage"] == 0
    finally:
        _stop(c)


def test_watchlist_with_authors():
    meta = make_sqlite(META_SCHEMA)
    meta.execute(
        "INSERT INTO author_profiles (author_handle, org, last_seen) VALUES (?, ?, datetime('now'))",
        ("@alice", "testorg"),
    )
    meta.execute(
        "INSERT INTO author_profiles (author_handle, org, last_seen) VALUES (?, ?, datetime('now', '-30 days'))",
        ("@bob", "testorg"),
    )
    meta.execute(
        "INSERT INTO scan_runs (org, completed_at, mode) VALUES (?, datetime('now'), 'full')",
        ("testorg",),
    )
    meta.commit()

    c = _make_client(meta)
    try:
        resp = c.get("/api/meta/watchlist/testorg")
        data = resp.json()
        assert data["total_authors"] == 2
        assert data["stale_authors"] == 1
        assert data["coverage"] == 0.5
        assert data["last_scan"] is not None
        assert data["total_scans"] == 1
    finally:
        _stop(c)
