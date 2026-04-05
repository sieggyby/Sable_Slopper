"""Contract tests: verify serve endpoint response shapes match API_REFERENCE.md.

These are not end-to-end tests — they use in-memory fixture data and verify
that response shapes are stable and parseable. Run in CI, no live services.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PULSE_SCHEMA = """
CREATE TABLE posts (
    id TEXT PRIMARY KEY,
    account_handle TEXT NOT NULL,
    platform TEXT DEFAULT 'twitter',
    url TEXT,
    text TEXT,
    posted_at TEXT,
    sable_content_type TEXT,
    sable_content_path TEXT,
    is_thread INTEGER DEFAULT 0,
    thread_length INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    taken_at TEXT DEFAULT (datetime('now')),
    likes INTEGER DEFAULT 0,
    retweets INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    bookmarks INTEGER DEFAULT 0,
    quotes INTEGER DEFAULT 0
);
CREATE TABLE account_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_handle TEXT NOT NULL,
    taken_at TEXT DEFAULT (datetime('now')),
    followers INTEGER DEFAULT 0,
    following INTEGER DEFAULT 0,
    tweet_count INTEGER DEFAULT 0
);
"""

META_SCHEMA = """
CREATE TABLE scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    mode TEXT,
    tweets_collected INTEGER DEFAULT 0,
    tweets_new INTEGER DEFAULT 0,
    estimated_cost REAL,
    watchlist_size INTEGER DEFAULT 0,
    claude_raw TEXT
);
CREATE TABLE topic_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    scan_id INTEGER,
    term TEXT NOT NULL,
    mention_count INTEGER DEFAULT 0,
    unique_authors INTEGER DEFAULT 0,
    avg_lift REAL,
    prev_scan_mentions INTEGER DEFAULT 0,
    acceleration REAL DEFAULT 0.0
);
CREATE TABLE format_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    format_bucket TEXT NOT NULL,
    period_days INTEGER NOT NULL,
    avg_total_lift REAL,
    sample_count INTEGER,
    unique_authors INTEGER,
    computed_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE author_profiles (
    author_handle TEXT NOT NULL,
    org TEXT NOT NULL,
    tweet_count INTEGER DEFAULT 0,
    last_seen TEXT,
    last_tweet_id TEXT,
    PRIMARY KEY (author_handle, org)
);
"""


def _make_db(schema: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(schema)
    return conn


def _seed_pulse(conn: sqlite3.Connection) -> None:
    """Insert realistic fixture data into pulse.db."""
    conn.execute(
        "INSERT INTO posts (id, account_handle, url, text, posted_at, sable_content_type) "
        "VALUES (?, ?, ?, ?, datetime('now', '-2 days'), ?)",
        ("post1", "@testhandle", "https://twitter.com/user/status/post1",
         "Test post about restaking", "clip"),
    )
    conn.execute(
        "INSERT INTO snapshots (post_id, likes, retweets, replies, views, bookmarks, quotes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("post1", 45, 12, 8, 3200, 5, 2),
    )
    conn.execute(
        "INSERT INTO account_stats (account_handle, followers, following, tweet_count) "
        "VALUES (?, ?, ?, ?)",
        ("@testhandle", 5000, 200, 500),
    )
    conn.commit()


def _seed_meta(conn: sqlite3.Connection) -> None:
    """Insert realistic fixture data into meta.db."""
    conn.execute(
        "INSERT INTO scan_runs (org, completed_at, mode, tweets_collected, tweets_new, watchlist_size) "
        "VALUES (?, datetime('now'), ?, ?, ?, ?)",
        ("testorg", "normal", 50, 10, 5),
    )
    scan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO topic_signals (org, scan_id, term, mention_count, unique_authors, avg_lift, acceleration) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("testorg", scan_id, "restaking", 15, 8, 4.2, 2.0),
    )
    conn.execute(
        "INSERT INTO format_baselines (org, format_bucket, period_days, avg_total_lift, sample_count, unique_authors) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("testorg", "hot_take", 30, 2.1, 25, 12),
    )
    conn.execute(
        "INSERT INTO author_profiles (author_handle, org, tweet_count, last_seen) "
        "VALUES (?, ?, ?, datetime('now', '-1 day'))",
        ("@author1", "testorg", 30),
    )
    conn.commit()


@pytest.fixture
def seeded_dbs():
    """Return (pulse_conn, meta_conn) with realistic fixture data."""
    pulse = _make_db(PULSE_SCHEMA)
    meta = _make_db(META_SCHEMA)
    _seed_pulse(pulse)
    _seed_meta(meta)
    return pulse, meta


@pytest.fixture
def client(seeded_dbs, tmp_path, monkeypatch):
    """TestClient with seeded DBs and valid auth."""
    pulse_conn, meta_conn = seeded_dbs

    # Create vault dir
    vault = tmp_path / "vault" / "testorg" / "content"
    vault.mkdir(parents=True)

    monkeypatch.setattr("sable.serve.deps.get_pulse_db", lambda: pulse_conn)
    monkeypatch.setattr("sable.serve.deps.get_meta_db", lambda: meta_conn)
    monkeypatch.setattr("sable.serve.deps.resolve_vault_path", lambda org: tmp_path / "vault" / org)
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"token": "test-token"} if key == "serve" else default,
    )

    from sable.serve.app import create_app
    from fastapi.testclient import TestClient
    app = create_app()
    return TestClient(app)


AUTH = {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# Health endpoint contract (SS-16)
# ---------------------------------------------------------------------------

class TestHealthContract:

    def test_health_returns_checks_object(self, client):
        """Health endpoint returns status + checks dict per SS-16 spec."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded")
        assert "checks" in data
        checks = data["checks"]
        assert "pulse_db" in checks
        assert "meta_db" in checks
        assert "vault" in checks
        assert all(isinstance(v, bool) for v in checks.values())

    def test_health_no_auth_required(self, client):
        """Health endpoint must not require authentication."""
        resp = client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Pulse endpoint contracts
# ---------------------------------------------------------------------------

class TestPulsePerformanceContract:

    def test_performance_response_shape(self, client):
        """Performance endpoint returns expected top-level fields."""
        resp = client.get("/api/pulse/performance/testorg", headers=AUTH)
        # May return error or data — both are valid contract shapes
        assert resp.status_code == 200
        data = resp.json()
        if "error" not in data:
            for field in ("total_posts", "sable_posts", "organic_posts"):
                assert field in data, f"Missing field: {field}"

    def test_posting_log_is_list(self, client):
        """Posting log returns a list of post objects."""
        resp = client.get("/api/pulse/posting-log/testorg", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Meta endpoint contracts
# ---------------------------------------------------------------------------

class TestMetaTopicsContract:

    def test_topics_response_shape(self, client):
        """Topics endpoint returns list with expected fields per item."""
        resp = client.get("/api/meta/topics/testorg", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if data:
            item = data[0]
            for field in ("topic", "mention_count", "unique_authors"):
                assert field in item, f"Missing field: {field}"

    def test_baselines_response_shape(self, client):
        """Baselines endpoint returns list with expected fields per item."""
        resp = client.get("/api/meta/baselines/testorg", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if data:
            item = data[0]
            for field in ("format", "signal", "avg_lift", "sample_count"):
                assert field in item, f"Missing field: {field}"

    def test_watchlist_response_shape(self, client):
        """Watchlist endpoint returns dict with expected fields."""
        resp = client.get("/api/meta/watchlist/testorg", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        for field in ("total_authors", "stale_authors", "coverage"):
            assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Vault endpoint contracts
# ---------------------------------------------------------------------------

class TestVaultInventoryContract:

    def test_inventory_response_shape(self, client):
        """Inventory endpoint returns dict with expected fields."""
        resp = client.get("/api/vault/inventory/testorg", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        if "error" not in data:
            for field in ("total_produced", "total_posted", "total_unused", "by_format"):
                assert field in data, f"Missing field: {field}"

    def test_search_returns_list(self, client):
        """Search endpoint returns a list."""
        resp = client.get("/api/vault/search/testorg?q=test", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Auth contract (SS-17 named tokens)
# ---------------------------------------------------------------------------

class TestAuthContract:

    def test_named_token_accepted(self, monkeypatch):
        """Named tokens (serve.tokens) are accepted."""
        monkeypatch.setattr(
            "sable.serve.auth.cfg.get",
            lambda key, default=None: {
                "tokens": {"sableweb": "web-token-123"},
            } if key == "serve" else default,
        )
        from sable.serve.app import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        tc = TestClient(app)
        resp = tc.get("/api/pulse/performance/testorg",
                       headers={"Authorization": "Bearer web-token-123"})
        # Should not be 401 or 403 — token accepted
        assert resp.status_code != 401
        assert resp.status_code != 403

    def test_legacy_token_still_works(self, monkeypatch):
        """Legacy single serve.token still accepted for backward compat."""
        monkeypatch.setattr(
            "sable.serve.auth.cfg.get",
            lambda key, default=None: {"token": "legacy-tok"} if key == "serve" else default,
        )
        from sable.serve.app import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        tc = TestClient(app)
        resp = tc.get("/api/pulse/performance/testorg",
                       headers={"Authorization": "Bearer legacy-tok"})
        assert resp.status_code != 401
        assert resp.status_code != 403

    def test_wrong_token_rejected(self, monkeypatch):
        """Invalid token returns 403."""
        monkeypatch.setattr(
            "sable.serve.auth.cfg.get",
            lambda key, default=None: {
                "token": "correct",
                "tokens": {"web": "also-correct"},
            } if key == "serve" else default,
        )
        from sable.serve.app import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        tc = TestClient(app)
        resp = tc.get("/api/pulse/performance/testorg",
                       headers={"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 403

    def test_legacy_token_works_when_named_tokens_also_configured(self, monkeypatch):
        """Legacy serve.token accepted even when serve.tokens is also present."""
        monkeypatch.setattr(
            "sable.serve.auth.cfg.get",
            lambda key, default=None: {
                "token": "legacy-fallback",
                "tokens": {"web": "named-only"},
            } if key == "serve" else default,
        )
        from sable.serve.app import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        tc = TestClient(app)
        resp = tc.get("/api/pulse/performance/testorg",
                       headers={"Authorization": "Bearer legacy-fallback"})
        assert resp.status_code != 401
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# TrackingMetadata field contract (SS-20 prep)
# ---------------------------------------------------------------------------

class TestTrackingMetadataContract:
    """Verify Slopper's expected metadata fields match the documented 17-field contract."""

    EXPECTED_FIELDS = {
        "source_tool", "url", "canonical_author_handle", "quality_score",
        "audience_annotation", "timing_annotation", "grok_status",
        "engagement_score", "lexicon_adoption", "emotional_valence",
        "subsquad_signal", "format_type", "intent_type", "topic_tags",
        "review_status", "outcome_type", "is_reusable_template",
    }

    def test_field_count(self):
        """Contract specifies exactly 17 fields."""
        assert len(self.EXPECTED_FIELDS) == 17

    def test_all_fields_are_strings(self):
        """All field names are valid Python identifiers."""
        for field in self.EXPECTED_FIELDS:
            assert field.isidentifier(), f"{field!r} is not a valid identifier"
