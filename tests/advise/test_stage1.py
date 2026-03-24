"""Tests for stage1.py warning blocks (bare-except parse failure fixes)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from sable.advise.stage1 import assemble_input


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_platform_conn():
    """Minimal in-memory sable.db with required tables."""
    from sable.platform.db import ensure_schema
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Test 1: pulse freshness parse failure logs a warning and sets pulse_available=False
# ---------------------------------------------------------------------------

def test_pulse_freshness_parse_failure_warns(tmp_path, monkeypatch, caplog):
    """Bad post_freshness value → WARNING logged, pulse_available=False."""
    import sqlite3 as _sqlite3

    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    conn = _make_platform_conn()

    # Build a minimal pulse.db with an unparseable taken_at timestamp
    pulse_db = tmp_path / "pulse.db"
    pulse_conn = _sqlite3.connect(str(pulse_db))
    pulse_conn.execute("""
        CREATE TABLE posts (
            id TEXT PRIMARY KEY, account_handle TEXT,
            text TEXT, posted_at TEXT, sable_content_type TEXT
        )
    """)
    pulse_conn.execute("""
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT, taken_at TEXT,
            likes INTEGER DEFAULT 0, retweets INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0, views INTEGER DEFAULT 0,
            bookmarks INTEGER DEFAULT 0, quotes INTEGER DEFAULT 0
        )
    """)
    # Insert a post with a snapshot whose taken_at is unparseable
    # Note: assemble_input is called with normalized_handle 'alice' (no @)
    pulse_conn.execute(
        "INSERT INTO posts VALUES ('p1', 'alice', 'hello', '2026-03-20T00:00:00', NULL)"
    )
    pulse_conn.execute(
        "INSERT INTO snapshots (post_id, taken_at, likes) VALUES ('p1', 'NOT_A_DATE', 10)"
    )
    pulse_conn.commit()
    pulse_conn.close()

    monkeypatch.setattr("sable.shared.paths.pulse_db_path", lambda: pulse_db)
    monkeypatch.setattr("sable.shared.paths.meta_db_path", lambda: tmp_path / "meta.db")

    with caplog.at_level(logging.WARNING, logger="sable.advise.stage1"):
        result = assemble_input("alice", "testorg", conn)

    # pulse_available should be False (stale due to parse failure)
    assert result["pulse_available"] is False
    # Warning should have been logged
    stage1_warnings = [r for r in caplog.records if "stage1 pulse freshness" in r.message]
    assert len(stage1_warnings) >= 1, "Expected WARNING for pulse freshness parse failure"

    conn.close()


# ---------------------------------------------------------------------------
# Test 2: meta scan-date parse failure logs a warning and sets meta_stale=True
# ---------------------------------------------------------------------------

def test_meta_scandate_parse_failure_warns(tmp_path, monkeypatch, caplog):
    """Bad scan_date in meta.db → WARNING logged, meta_stale=True."""
    import sqlite3 as _sqlite3

    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    conn = _make_platform_conn()

    # Build a minimal meta.db with bad completed_at
    meta_db = tmp_path / "meta.db"
    meta_conn = _sqlite3.connect(str(meta_db))
    meta_conn.execute("""
        CREATE TABLE scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org TEXT, completed_at TEXT, status TEXT
        )
    """)
    meta_conn.execute("""
        CREATE TABLE topic_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org TEXT, scan_id INTEGER, term TEXT,
            mention_count INTEGER, unique_authors INTEGER,
            avg_lift REAL, acceleration REAL
        )
    """)
    meta_conn.execute("""
        CREATE TABLE format_baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org TEXT, period_days INTEGER,
            format_bucket TEXT, avg_total_lift REAL, sample_count INTEGER
        )
    """)
    # Insert a scan run with unparseable completed_at
    meta_conn.execute(
        "INSERT INTO scan_runs (org, completed_at, status) VALUES ('testorg', 'BAD_DATE', 'completed')"
    )
    meta_conn.commit()
    meta_conn.close()

    monkeypatch.setattr("sable.shared.paths.pulse_db_path", lambda: tmp_path / "pulse.db")
    monkeypatch.setattr("sable.shared.paths.meta_db_path", lambda: meta_db)

    with caplog.at_level(logging.WARNING, logger="sable.advise.stage1"):
        result = assemble_input("alice", "testorg", conn)

    assert result["meta_stale"] is True
    stage1_warnings = [r for r in caplog.records if "stage1 meta scan-date" in r.message]
    assert len(stage1_warnings) >= 1, "Expected WARNING for meta scan-date parse failure"

    conn.close()


# ---------------------------------------------------------------------------
# Test 3: tracker metadata_json parse failure logs warning, row still included
# ---------------------------------------------------------------------------

def test_tracker_metadata_parse_failure_warns(tmp_path, monkeypatch, caplog):
    """Invalid metadata_json on content_items row → WARNING logged, row included with meta={}."""
    from datetime import datetime, timezone

    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    conn = _make_platform_conn()

    # Insert a content_items row with invalid JSON — should warn and fall back to meta={}
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO content_items (item_id, org_id, content_type, body, metadata_json, created_at)
           VALUES ('bad1', 'testorg', 'tweet', 'bad row body', 'NOT_VALID_JSON', ?)""",
        (now,)
    )
    conn.commit()

    monkeypatch.setattr("sable.shared.paths.pulse_db_path", lambda: tmp_path / "pulse.db")
    monkeypatch.setattr("sable.shared.paths.meta_db_path", lambda: tmp_path / "meta.db")

    with caplog.at_level(logging.WARNING, logger="sable.advise.stage1"):
        assemble_input("alice", "testorg", conn)

    stage1_warnings = [r for r in caplog.records if "stage1 tracker metadata_json" in r.message]
    assert len(stage1_warnings) >= 1, "Expected WARNING for tracker metadata_json parse failure"

    conn.close()
