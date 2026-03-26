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
        "INSERT INTO posts VALUES ('p1', '@alice', 'hello', '2026-03-20T00:00:00', NULL)"
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
# Test 1b: pulse freshness + post_freshness populate when handle normalizes correctly
# ---------------------------------------------------------------------------

def test_pulse_last_track_populates_for_at_handle(tmp_path, monkeypatch):
    """assemble_input with bare 'alice' normalizes to '@alice' for both pulse queries."""
    import sqlite3 as _sqlite3
    from datetime import datetime, timezone

    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    conn = _make_platform_conn()

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
    # Insert with @alice — must match the normalized form used by both queries
    now_iso = datetime.now(timezone.utc).isoformat()
    pulse_conn.execute(
        "INSERT INTO posts VALUES ('p1', '@alice', 'hello', ?, NULL)",
        (now_iso,)
    )
    pulse_conn.execute(
        "INSERT INTO snapshots (post_id, taken_at, likes) VALUES ('p1', ?, 10)",
        (now_iso,)
    )
    pulse_conn.commit()
    pulse_conn.close()

    monkeypatch.setattr("sable.shared.paths.pulse_db_path", lambda: pulse_db)
    monkeypatch.setattr("sable.shared.paths.meta_db_path", lambda: tmp_path / "meta.db")

    result = assemble_input("alice", "testorg", conn)

    assert result["data_freshness"]["pulse_last_track"] is not None
    assert result["post_freshness"] is not None

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


# ---------------------------------------------------------------------------
# Test 4: content_items ordered by posted_at not created_at (COALESCE fix)
# ---------------------------------------------------------------------------

def test_content_items_ordered_by_posted_at_not_created_at(tmp_path, monkeypatch):
    """Item with older created_at but newer posted_at should appear first."""
    from datetime import datetime, timezone, timedelta
    import json

    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    conn = _make_platform_conn()

    now = datetime.now(timezone.utc)
    # Item A: created_at is 5d ago (newest ingestion), but posted_at is 13d ago (oldest source)
    item_a_created = (now - timedelta(days=5)).isoformat()
    item_a_posted = (now - timedelta(days=13)).isoformat()
    # Item B: created_at is 10d ago (older ingestion), but posted_at is 2d ago (newest source)
    item_b_created = (now - timedelta(days=10)).isoformat()
    item_b_posted = (now - timedelta(days=2)).isoformat()

    meta_a = json.dumps({"source_tool": "sable_tracking"})
    meta_b = json.dumps({"source_tool": "sable_tracking"})

    conn.execute(
        """INSERT INTO content_items (item_id, org_id, content_type, body, metadata_json, created_at, posted_at)
           VALUES ('item-a', 'testorg', 'tweet', 'item A body', ?, ?, ?)""",
        (meta_a, item_a_created, item_a_posted),
    )
    conn.execute(
        """INSERT INTO content_items (item_id, org_id, content_type, body, metadata_json, created_at, posted_at)
           VALUES ('item-b', 'testorg', 'tweet', 'item B body', ?, ?, ?)""",
        (meta_b, item_b_created, item_b_posted),
    )
    conn.commit()

    monkeypatch.setattr("sable.shared.paths.pulse_db_path", lambda: tmp_path / "pulse.db")
    monkeypatch.setattr("sable.shared.paths.meta_db_path", lambda: tmp_path / "meta.db")

    result = assemble_input("alice", "testorg", conn)

    items = result["content_items"]
    assert len(items) == 2, f"Expected 2 content items, got {len(items)}"
    # Item B has newer posted_at so it should appear first
    assert items[0]["body"] == "item B body", (
        f"Expected item B (newer posted_at) first, got: {items[0]['body']}"
    )
    assert items[1]["body"] == "item A body"

    conn.close()
