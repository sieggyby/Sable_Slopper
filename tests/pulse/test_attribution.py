"""Tests for sable/pulse/attribution.py (Slice B)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sable.pulse.attribution import ContentAttribution, compute_attribution, render_attribution_report


# ---------------------------------------------------------------------------
# Shared schema + helpers (reuse pattern from test_account_report.py)
# ---------------------------------------------------------------------------

_PULSE_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
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
CREATE TABLE IF NOT EXISTS snapshots (
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
"""

_FORMAT_BASELINES_SCHEMA = """
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
"""


def _make_pulse_db(tmp_path: Path) -> Path:
    path = tmp_path / "pulse.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_PULSE_SCHEMA)
    conn.commit()
    conn.close()
    return path


def _make_meta_db(tmp_path: Path) -> Path:
    path = tmp_path / "meta.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_FORMAT_BASELINES_SCHEMA)
    conn.commit()
    conn.close()
    return path


def _recent_iso(days_ago: int = 1) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def _insert_post(conn: sqlite3.Connection, post_id: str, handle: str,
                 ct: Optional[str] = "text", days_ago: int = 1,
                 content_path: Optional[str] = None) -> None:
    conn.execute(
        """INSERT INTO posts (id, account_handle, text, posted_at, sable_content_type, sable_content_path)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (post_id, handle, f"text of {post_id}", _recent_iso(days_ago), ct, content_path),
    )


def _insert_snapshot(conn: sqlite3.Connection, post_id: str,
                     likes: int = 0, retweets: int = 0, replies: int = 0,
                     views: int = 0, bookmarks: int = 0, quotes: int = 0) -> None:
    conn.execute(
        """INSERT INTO snapshots (post_id, likes, retweets, replies, views, bookmarks, quotes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (post_id, likes, retweets, replies, views, bookmarks, quotes),
    )


def _insert_baseline(conn: sqlite3.Connection, org: str, bucket: str,
                     computed_at: str, avg_lift: float = 1.5) -> None:
    conn.execute(
        """INSERT INTO format_baselines
           (org, format_bucket, period_days, avg_total_lift, sample_count, unique_authors, computed_at)
           VALUES (?, ?, 7, ?, 10, 5, ?)""",
        (org, bucket, avg_lift, computed_at),
    )
    conn.commit()


# typing import for _insert_post signature
from typing import Optional


# ---------------------------------------------------------------------------
# Test 1: basic mixed content
# ---------------------------------------------------------------------------

def test_basic_attribution_mixed_content(tmp_path):
    """5 sable (clip) posts + 5 organic posts, each with likes=10."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    for i in range(5):
        _insert_post(conn, f"s{i}", "@alice", "clip")
        _insert_snapshot(conn, f"s{i}", likes=10)
    for i in range(5):
        _insert_post(conn, f"o{i}", "@alice", None)
        _insert_snapshot(conn, f"o{i}", likes=10)
    conn.commit()
    conn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db)
    assert attr.total_posts == 10
    assert attr.sable_posts == 5
    assert attr.organic_posts == 5
    assert attr.sable_share_of_posts == pytest.approx(0.5)
    assert attr.sable_share_of_engagement == pytest.approx(0.5)
    # Each post: likes=10 → engagement = 10*1 = 10
    assert attr.sable_avg_engagement == pytest.approx(10.0)
    assert attr.organic_avg_engagement == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Test 2: no sable content
# ---------------------------------------------------------------------------

def test_no_sable_content(tmp_path):
    """10 organic posts; assert sable_posts=0, sable_share_of_engagement=0.0, sable_lift_vs_organic=None."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    for i in range(10):
        _insert_post(conn, f"o{i}", "@alice", None)
        _insert_snapshot(conn, f"o{i}", likes=20)
    conn.commit()
    conn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db)
    assert attr.sable_posts == 0
    assert attr.sable_share_of_engagement == pytest.approx(0.0)
    assert attr.sable_lift_vs_organic is None


# ---------------------------------------------------------------------------
# Test 3: no organic content
# ---------------------------------------------------------------------------

def test_no_organic_content(tmp_path):
    """5 sable only; organic_posts=0, sable_lift_vs_organic=None."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    for i in range(5):
        _insert_post(conn, f"s{i}", "@alice", "meme")
        _insert_snapshot(conn, f"s{i}", likes=30)
    conn.commit()
    conn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db)
    assert attr.organic_posts == 0
    assert attr.sable_lift_vs_organic is None


# ---------------------------------------------------------------------------
# Test 4: multiple snapshots uses latest
# ---------------------------------------------------------------------------

def test_multiple_snapshots_uses_latest(tmp_path):
    """1 post with 3 snapshots (ascending id); engagement = highest-id snapshot."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _insert_post(conn, "p1", "@alice", "text")
    # Three snapshots; latest has likes=100
    _insert_snapshot(conn, "p1", likes=10)
    _insert_snapshot(conn, "p1", likes=50)
    _insert_snapshot(conn, "p1", likes=100)
    conn.commit()
    conn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db)
    assert attr.sable_posts == 1
    # engagement = 100 * 1 = 100
    assert attr.sable_engagement == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Test 5: meta-informed classification
# ---------------------------------------------------------------------------

def test_meta_informed_classification(tmp_path):
    """Baselines for short_clip and standalone_text before post date.
    2 clip posts + 2 text posts → only clips are meta-informed (both buckets have baselines,
    but the test checks that clips are classified into short_clip which has a baseline)."""
    db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    conn = sqlite3.connect(str(db))
    for i in range(2):
        _insert_post(conn, f"c{i}", "@alice", "clip", days_ago=5)
        _insert_snapshot(conn, f"c{i}", likes=20)
    for i in range(2):
        _insert_post(conn, f"t{i}", "@alice", "text", days_ago=5)
        _insert_snapshot(conn, f"t{i}", likes=10)
    conn.commit()
    conn.close()

    # Only short_clip has a baseline (not standalone_text)
    mconn = sqlite3.connect(str(meta_db))
    _insert_baseline(mconn, "testorg", "short_clip", _recent_iso(10), avg_lift=2.0)
    mconn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db, meta_db_path=meta_db, org="testorg")
    assert attr.meta_available is True
    # Only the 2 clip posts (→ short_clip) are meta-informed
    assert attr.meta_informed_posts == 2


# ---------------------------------------------------------------------------
# Test 6: weekly breakdown three weeks
# ---------------------------------------------------------------------------

def test_weekly_breakdown_three_weeks(tmp_path):
    """Posts in 3 different ISO weeks → weekly_breakdown has 3 entries."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))

    # Spread posts across 3 weeks (7+ days apart)
    for week_offset, days_ago in enumerate([2, 9, 16]):
        pid = f"p{week_offset}"
        _insert_post(conn, pid, "@alice", "text", days_ago=days_ago)
        _insert_snapshot(conn, pid, likes=5)
    conn.commit()
    conn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db)
    assert len(attr.weekly_breakdown) == 3
    for w in attr.weekly_breakdown:
        assert "week" in w
        assert w["week"].startswith("20")


# ---------------------------------------------------------------------------
# Test 7: date filtering
# ---------------------------------------------------------------------------

def test_date_filtering(tmp_path):
    """Posts outside the window are excluded."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _insert_post(conn, "recent", "@alice", "text", days_ago=5)
    _insert_snapshot(conn, "recent", likes=10)
    _insert_post(conn, "old", "@alice", "text", days_ago=45)
    _insert_snapshot(conn, "old", likes=10)
    conn.commit()
    conn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db)
    assert attr.total_posts == 1


# ---------------------------------------------------------------------------
# Test 8: no meta db (org=None)
# ---------------------------------------------------------------------------

def test_no_meta_db(tmp_path):
    """Call with org=None → meta_available=False, meta_informed_posts=0, no exception."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _insert_post(conn, "s1", "@alice", "clip")
    _insert_snapshot(conn, "s1", likes=10)
    conn.commit()
    conn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db, org=None)
    assert attr.meta_available is False
    assert attr.meta_informed_posts == 0


# ---------------------------------------------------------------------------
# Test A: corrupt meta.db logs warning, does not raise
# ---------------------------------------------------------------------------

def test_corrupt_meta_db_logs_warning(tmp_path, caplog):
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _insert_post(conn, "s1", "@alice", "clip")
    _insert_snapshot(conn, "s1", likes=10)
    conn.commit()
    conn.close()

    bad_meta = tmp_path / "bad.db"
    bad_meta.write_bytes(b"not a sqlite database")

    import logging
    with caplog.at_level(logging.WARNING, logger="sable.pulse.attribution"):
        attr = compute_attribution("alice", days=30, pulse_db_path=db,
                                   meta_db_path=bad_meta, org="testorg")

    assert attr.meta_available is False
    assert any("meta.db" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Test B: thin bucket shows "n/a (thin)" not a lift number
# ---------------------------------------------------------------------------

def test_format_table_thin_sample_shows_no_lift(tmp_path):
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    # 1 sable clip, 1 organic post — below _MIN_LIFT_SAMPLE=3
    _insert_post(conn, "s1", "@alice", "clip")
    _insert_snapshot(conn, "s1", likes=50)
    _insert_post(conn, "o1", "@alice", None)
    _insert_snapshot(conn, "o1", likes=5)
    conn.commit()
    conn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db)
    report = render_attribution_report(attr)
    format_section = report.split("Format Breakdown")[1].split("Weekly")[0]
    assert "n/a (thin)" in format_section or "n/a" in format_section
    assert "+" not in format_section


# ---------------------------------------------------------------------------
# Test C: comparison caveat appears in rendered report
# ---------------------------------------------------------------------------

def test_render_includes_comparison_caveat(tmp_path):
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _insert_post(conn, "s1", "@alice", "clip")
    _insert_snapshot(conn, "s1", likes=50)
    _insert_post(conn, "o1", "@alice", None)
    _insert_snapshot(conn, "o1", likes=10)
    conn.commit()
    conn.close()

    attr = compute_attribution("alice", days=30, pulse_db_path=db)
    report = render_attribution_report(attr)
    assert "not a controlled comparison" in report
