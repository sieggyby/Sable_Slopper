"""Tests for sable.cadence.combine — silence gradient computation."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from sable.pulse.meta.db import _SCHEMA
from sable.cadence.combine import (
    compute_silence_gradient,
    W_VOL, W_ENG, W_FMT,
    MIN_WINDOW_DAYS,
)

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int = 0) -> str:
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _insert(conn, org, author, text="test", days_ago=0, total_lift=5.0,
            format_bucket="standalone_text"):
    tid = str(uuid.uuid4())[:12]
    conn.execute(
        """INSERT INTO scanned_tweets
           (tweet_id, org, author_handle, posted_at, text, total_lift, format_bucket,
            likes, replies, reposts, quotes, bookmarks)
           VALUES (?, ?, ?, ?, ?, ?, ?, 10, 5, 3, 1, 0)""",
        (tid, org, author, _ts(days_ago), text, total_lift, format_bucket),
    )
    conn.commit()


def test_weight_sum():
    """Signal weights sum to 1.0."""
    assert W_VOL + W_ENG + W_FMT == pytest.approx(1.0)


def test_basic_gradient():
    """Author with declining volume gets positive gradient."""
    conn = _make_conn()
    # Prior half (days 16-30): 10 posts
    for i in range(10):
        _insert(conn, "org", "@decl", days_ago=16 + i, total_lift=5.0)
    # Recent half (days 0-15): 2 posts (big drop)
    for i in range(2):
        _insert(conn, "org", "@decl", days_ago=i, total_lift=3.0)

    results = compute_silence_gradient("org", window_days=30, conn=conn)
    assert len(results) == 1
    assert results[0]["author_handle"] == "@decl"
    assert results[0]["silence_gradient"] > 0


def test_stable_author_low_gradient():
    """Author with consistent posting gets low gradient."""
    conn = _make_conn()
    for i in range(30):
        _insert(conn, "org", "@stable", days_ago=i, total_lift=5.0)

    results = compute_silence_gradient("org", window_days=30, conn=conn)
    assert len(results) == 1
    assert results[0]["silence_gradient"] < 0.3


def test_all_insufficient_excluded():
    """Author with too few posts in both halves is excluded."""
    conn = _make_conn()
    # Only 1 post in each half → volume works but eng and fmt insufficient
    _insert(conn, "org", "@sparse", days_ago=1)
    _insert(conn, "org", "@sparse", days_ago=20)

    results = compute_silence_gradient("org", window_days=30, conn=conn)
    # Should still be included since volume signal is never insufficient
    assert len(results) == 1


def test_weight_redistribution():
    """When engagement is insufficient, weights redistribute proportionally."""
    conn = _make_conn()
    # Prior half: 3 posts (below MIN_ROWS_PER_HALF for engagement)
    for i in range(3):
        _insert(conn, "org", "@low", days_ago=16 + i, total_lift=5.0)
    # Recent half: 1 post
    _insert(conn, "org", "@low", days_ago=1, total_lift=2.0)

    results = compute_silence_gradient("org", window_days=30, conn=conn)
    assert len(results) == 1
    r = results[0]
    # engagement should be insufficient
    assert r["insufficient_data"] is not None
    assert "engagement" in r["insufficient_data"]


def test_sorted_by_gradient_desc():
    """Results sorted by silence_gradient descending."""
    conn = _make_conn()
    # Author A: declining
    for i in range(10):
        _insert(conn, "org", "@declining", days_ago=16 + i, total_lift=5.0)
    _insert(conn, "org", "@declining", days_ago=1, total_lift=1.0)

    # Author B: stable
    for i in range(30):
        _insert(conn, "org", "@stable", days_ago=i, total_lift=5.0)

    results = compute_silence_gradient("org", window_days=30, conn=conn)
    assert len(results) == 2
    assert results[0]["silence_gradient"] >= results[1]["silence_gradient"]


def test_odd_window_rejected():
    """Odd window_days raises ValueError."""
    conn = _make_conn()
    with pytest.raises(ValueError, match="even"):
        compute_silence_gradient("org", window_days=31, conn=conn)


def test_small_window_rejected():
    """Window below MIN_WINDOW_DAYS raises ValueError."""
    conn = _make_conn()
    with pytest.raises(ValueError, match=str(MIN_WINDOW_DAYS)):
        compute_silence_gradient("org", window_days=4, conn=conn)


def test_empty_org():
    """Empty org returns empty list."""
    conn = _make_conn()
    assert compute_silence_gradient("empty", window_days=30, conn=conn) == []
