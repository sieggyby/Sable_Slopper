"""Tests for --skip-if-fresh flag on meta scan and the meta status subcommand."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sable.pulse.meta.cli import meta_group


# ---------------------------------------------------------------------------
# Shared DB helpers
# ---------------------------------------------------------------------------

_SCAN_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS scan_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    org              TEXT NOT NULL,
    started_at       TEXT DEFAULT (datetime('now')),
    completed_at     TEXT,
    mode             TEXT,
    tweets_collected INTEGER DEFAULT 0,
    tweets_new       INTEGER DEFAULT 0,
    estimated_cost   REAL,
    watchlist_size   INTEGER DEFAULT 0,
    claude_raw       TEXT
);
CREATE TABLE IF NOT EXISTS scanned_tweets (
    tweet_id TEXT PRIMARY KEY,
    author_handle TEXT NOT NULL,
    text TEXT,
    posted_at TEXT,
    format_bucket TEXT,
    attributes_json TEXT,
    likes INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0,
    quotes INTEGER DEFAULT 0,
    bookmarks INTEGER DEFAULT 0,
    video_views INTEGER DEFAULT 0,
    video_duration INTEGER,
    is_quote_tweet INTEGER DEFAULT 0,
    is_thread INTEGER DEFAULT 0,
    thread_length INTEGER DEFAULT 1,
    has_image INTEGER DEFAULT 0,
    has_video INTEGER DEFAULT 0,
    has_link INTEGER DEFAULT 0,
    author_followers INTEGER DEFAULT 0,
    author_median_likes REAL,
    author_median_replies REAL,
    author_median_reposts REAL,
    author_median_quotes REAL,
    author_median_total REAL,
    author_median_same_format REAL,
    likes_lift REAL,
    replies_lift REAL,
    reposts_lift REAL,
    quotes_lift REAL,
    total_lift REAL,
    format_lift REAL,
    author_quality_grade TEXT,
    author_quality_weight REAL,
    format_lift_reliable INTEGER DEFAULT 0,
    scan_id INTEGER,
    org TEXT
);
CREATE TABLE IF NOT EXISTS author_profiles (
    author_handle TEXT NOT NULL,
    org TEXT NOT NULL,
    tweet_count INTEGER DEFAULT 0,
    last_seen TEXT,
    last_tweet_id TEXT,
    PRIMARY KEY (author_handle, org)
);
CREATE TABLE IF NOT EXISTS format_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    format_bucket TEXT NOT NULL,
    period_days INTEGER NOT NULL,
    avg_total_lift REAL,
    sample_count INTEGER,
    unique_authors INTEGER,
    computed_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS topic_signals (
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
CREATE TABLE IF NOT EXISTS hook_pattern_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    org         TEXT NOT NULL,
    format_bucket TEXT NOT NULL,
    patterns_json TEXT NOT NULL,
    generated_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hook_patterns_key
    ON hook_pattern_cache (org, format_bucket);
CREATE TABLE IF NOT EXISTS viral_anatomies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    org            TEXT NOT NULL,
    tweet_id       TEXT NOT NULL,
    author_handle  TEXT NOT NULL,
    total_lift     REAL NOT NULL,
    format_bucket  TEXT NOT NULL,
    anatomy_json   TEXT NOT NULL,
    analyzed_at    TEXT NOT NULL,
    UNIQUE(org, tweet_id)
);
"""


class _NoClose:
    """Proxy that keeps an in-memory connection alive across helper calls."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.row_factory = conn.row_factory

    def execute(self, *a, **kw):
        return self._conn.execute(*a, **kw)

    def executemany(self, *a, **kw):
        return self._conn.executemany(*a, **kw)

    def executescript(self, *a, **kw):
        return self._conn.executescript(*a, **kw)

    def commit(self):
        return self._conn.commit()

    def close(self):
        pass  # no-op — keep in-memory DB alive

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *a):
        return self._conn.__exit__(*a)


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCAN_RUNS_SCHEMA)
    conn.commit()
    return conn


def _iso_hours_ago(hours: float) -> str:
    """Return an ISO 8601 UTC timestamp N hours in the past."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Test 1: skip when scan is recent
# ---------------------------------------------------------------------------

def test_skip_if_fresh_skips_when_recent(monkeypatch):
    """--skip-if-fresh 2 should skip when last scan was 1h ago."""
    conn = _make_conn()
    # Insert a completed scan 1 hour ago (no FAILED prefix → successful)
    conn.execute(
        "INSERT INTO scan_runs (org, completed_at, claude_raw) VALUES (?, ?, ?)",
        ("testorg", _iso_hours_ago(1), "some output"),
    )
    conn.commit()

    import sable.pulse.meta.db as db_mod
    import sable.pulse.meta.cli as cli_mod

    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    scanner_called = []

    def fake_scanner(*args, **kwargs):
        m = MagicMock()
        m.run.side_effect = lambda *a, **kw: scanner_called.append(True) or {}
        m.estimate_cost.return_value = {"accounts": 1, "estimated_requests": 1, "estimated_cost_usd": 0.0}
        return m

    monkeypatch.setattr(cli_mod, "Scanner" if hasattr(cli_mod, "Scanner") else "_sentinel",
                        fake_scanner, raising=False)

    with (
        patch("sable.pulse.meta.db.migrate"),
        patch("sable.pulse.meta.watchlist.list_watchlist",
              return_value=[{"handle": "@alice"}]),
        patch("sable.config.load_config", return_value={}),
        patch("sable.pulse.meta.scanner.Scanner", fake_scanner),
        patch("sable.pulse.meta.db.get_latest_successful_scan_at",
              side_effect=db_mod.get_latest_successful_scan_at),
    ):
        runner = CliRunner()
        result = runner.invoke(meta_group, ["scan", "--org", "testorg", "--skip-if-fresh", "2"])

    assert "skipped" in result.output.lower(), f"Expected 'skipped' in output: {result.output!r}"
    assert not scanner_called, "Scanner.run() should not have been called"


# ---------------------------------------------------------------------------
# Test 2: run when scan is stale
# ---------------------------------------------------------------------------

def test_skip_if_fresh_runs_when_stale(monkeypatch):
    """--skip-if-fresh 2 should proceed when last scan was 5h ago."""
    conn = _make_conn()
    conn.execute(
        "INSERT INTO scan_runs (org, completed_at, claude_raw) VALUES (?, ?, ?)",
        ("testorg", _iso_hours_ago(5), "some output"),
    )
    conn.commit()

    import sable.pulse.meta.db as db_mod

    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    scanner_called = []

    def fake_scanner_cls(*args, **kwargs):
        m = MagicMock()
        m._tweets_new = 0
        m._estimated_cost = 0.0
        m.run.side_effect = lambda scan_id: (
            scanner_called.append(True) or
            {"tweets_collected": 0, "tweets_new": 0, "estimated_cost": 0.0,
             "aborted": False, "failed_authors": []}
        )
        m.estimate_cost.return_value = {
            "accounts": 1, "estimated_requests": 1, "estimated_cost_usd": 0.0,
        }
        return m

    with (
        patch("sable.pulse.meta.db.migrate"),
        patch("sable.pulse.meta.db.create_scan_run", return_value=1),
        patch("sable.pulse.meta.db.complete_scan_run"),
        patch("sable.pulse.meta.db.get_scan_runs", return_value=[]),
        patch("sable.pulse.meta.db.get_tweets_for_scan", return_value=[]),
        patch("sable.pulse.meta.db.get_latest_successful_scan_at",
              side_effect=db_mod.get_latest_successful_scan_at),
        patch("sable.pulse.meta.watchlist.list_watchlist",
              return_value=[{"handle": "@alice"}]),
        patch("sable.config.load_config", return_value={}),
        patch("sable.pulse.meta.scanner.Scanner", fake_scanner_cls),
    ):
        runner = CliRunner()
        result = runner.invoke(meta_group, ["scan", "--org", "testorg", "--skip-if-fresh", "2"])

    assert scanner_called, (
        f"Scanner.run() should have been called (scan is stale). Output: {result.output!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: run when no history exists
# ---------------------------------------------------------------------------

def test_skip_if_fresh_runs_when_no_history(monkeypatch):
    """--skip-if-fresh 2 should proceed when there is no scan history."""
    conn = _make_conn()  # empty DB — no rows in scan_runs

    import sable.pulse.meta.db as db_mod

    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    scanner_called = []

    def fake_scanner_cls(*args, **kwargs):
        m = MagicMock()
        m._tweets_new = 0
        m._estimated_cost = 0.0
        m.run.side_effect = lambda scan_id: (
            scanner_called.append(True) or
            {"tweets_collected": 0, "tweets_new": 0, "estimated_cost": 0.0,
             "aborted": False, "failed_authors": []}
        )
        m.estimate_cost.return_value = {
            "accounts": 1, "estimated_requests": 1, "estimated_cost_usd": 0.0,
        }
        return m

    with (
        patch("sable.pulse.meta.db.migrate"),
        patch("sable.pulse.meta.db.create_scan_run", return_value=1),
        patch("sable.pulse.meta.db.complete_scan_run"),
        patch("sable.pulse.meta.db.get_scan_runs", return_value=[]),
        patch("sable.pulse.meta.db.get_tweets_for_scan", return_value=[]),
        patch("sable.pulse.meta.db.get_latest_successful_scan_at",
              side_effect=db_mod.get_latest_successful_scan_at),
        patch("sable.pulse.meta.watchlist.list_watchlist",
              return_value=[{"handle": "@alice"}]),
        patch("sable.config.load_config", return_value={}),
        patch("sable.pulse.meta.scanner.Scanner", fake_scanner_cls),
    ):
        runner = CliRunner()
        result = runner.invoke(meta_group, ["scan", "--org", "testorg", "--skip-if-fresh", "2"])

    assert scanner_called, (
        f"Scanner.run() should have been called (no history). Output: {result.output!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: meta status with no rows
# ---------------------------------------------------------------------------

def test_meta_status_empty(monkeypatch):
    """meta status should print 'No scans recorded' when DB is empty."""
    conn = _make_conn()

    import sable.pulse.meta.db as db_mod

    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    with patch("sable.pulse.meta.db.migrate"):
        runner = CliRunner()
        result = runner.invoke(meta_group, ["status"])

    assert result.exit_code == 0, f"Non-zero exit: {result.output!r}"
    assert "no scans recorded" in result.output.lower(), (
        f"Expected 'No scans recorded' in output: {result.output!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: meta status shows table with org rows
# ---------------------------------------------------------------------------

def test_meta_status_shows_table(monkeypatch):
    """meta status should list both orgs when 2 orgs have scan history."""
    conn = _make_conn()
    conn.executemany(
        "INSERT INTO scan_runs (org, completed_at, claude_raw) VALUES (?, ?, ?)",
        [
            ("alpha_org", _iso_hours_ago(3), "ok"),
            ("beta_org", _iso_hours_ago(10), "ok"),
        ],
    )
    conn.commit()

    import sable.pulse.meta.db as db_mod

    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    with patch("sable.pulse.meta.db.migrate"):
        runner = CliRunner()
        result = runner.invoke(meta_group, ["status"])

    assert result.exit_code == 0, f"Non-zero exit: {result.output!r}"
    assert "alpha_org" in result.output, f"Expected 'alpha_org' in output: {result.output!r}"
    assert "beta_org" in result.output, f"Expected 'beta_org' in output: {result.output!r}"
