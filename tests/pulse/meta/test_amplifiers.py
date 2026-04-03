"""Tests for sable.pulse.meta.amplifiers — watchlist amplifier scoring."""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from sable.pulse.meta.db import _SCHEMA
from sable.pulse.meta.amplifiers import (
    compute_amplifiers,
    _percentile_rank,
    AmplifierRow,
    W_RT_V,
    W_RPR,
    W_QTR,
)

from datetime import datetime, timedelta, timezone

# Use dates relative to now to avoid window-filter issues
_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int = 0) -> str:
    """Return a timestamp string `days_ago` days before now."""
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _insert_tweet(conn, org, author, posted_at, likes=10, replies=5, reposts=3,
                  quotes=1, bookmarks=2):
    """Insert a scanned_tweet row with known engagement."""
    import uuid
    tid = str(uuid.uuid4())[:12]
    conn.execute(
        """INSERT INTO scanned_tweets
           (tweet_id, org, author_handle, posted_at, likes, replies, reposts,
            quotes, bookmarks, text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'test')""",
        (tid, org, author, posted_at, likes, replies, reposts, quotes, bookmarks),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Percentile rank unit tests
# ---------------------------------------------------------------------------

def test_percentile_rank_basic():
    """Three distinct values produce 0.0, 0.5, 1.0 percentiles."""
    assert _percentile_rank([10, 20, 30]) == [0.0, 0.5, 1.0]


def test_percentile_rank_ties():
    """Tied values get the same percentile."""
    result = _percentile_rank([5, 5, 10])
    assert result[0] == result[1]
    assert result[2] == 1.0


def test_percentile_rank_single():
    """Single value → percentile 1.0."""
    assert _percentile_rank([42]) == [1.0]


def test_percentile_rank_empty():
    """Empty list → empty result."""
    assert _percentile_rank([]) == []


# ---------------------------------------------------------------------------
# Amplifier computation
# ---------------------------------------------------------------------------

@patch("sable.pulse.meta.amplifiers.sable_cfg")
def test_three_authors_ranked_correctly(mock_cfg):
    """Three authors with distinct profiles produce expected ranking."""
    mock_cfg.load_config.return_value = {}
    conn = _make_conn()

    # Author A: high reposts, low replies/quotes
    for i in range(5):
        _insert_tweet(conn, "test_org", "@high_rt", _ts(i),
                      likes=100, replies=1, reposts=50, quotes=0, bookmarks=0)
    # Author B: high replies, low reposts/quotes
    for i in range(5):
        _insert_tweet(conn, "test_org", "@high_rpr", _ts(i),
                      likes=10, replies=80, reposts=1, quotes=0, bookmarks=0)
    # Author C: high quotes
    for i in range(5):
        _insert_tweet(conn, "test_org", "@high_qtr", _ts(i),
                      likes=10, replies=1, reposts=1, quotes=50, bookmarks=0)

    results = compute_amplifiers("test_org", window_days=30, conn=conn)
    assert len(results) == 3
    # All should have rank assigned
    ranks = {r.author: r.rank for r in results}
    assert set(ranks.values()) == {1, 2, 3}
    # Each author should lead in their signal
    by_author = {r.author: r for r in results}
    assert by_author["@high_rt"].rt_v > by_author["@high_rpr"].rt_v
    assert by_author["@high_rpr"].rpr > by_author["@high_rt"].rpr
    assert by_author["@high_qtr"].qtr > by_author["@high_rt"].qtr


@patch("sable.pulse.meta.amplifiers.sable_cfg")
def test_single_author_gets_rank_1(mock_cfg):
    """Single author gets all percentiles = 1.0 and rank 1."""
    mock_cfg.load_config.return_value = {}
    conn = _make_conn()

    _insert_tweet(conn, "org", "@solo", _ts(1),
                  likes=10, replies=5, reposts=3, quotes=2, bookmarks=1)

    results = compute_amplifiers("org", window_days=30, conn=conn)
    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].amp_score == 1.0  # all percentiles = 1.0


@patch("sable.pulse.meta.amplifiers.sable_cfg")
def test_zero_engagement_rpr_is_zero(mock_cfg):
    """Author with zero total engagement gets RPR = 0 (no div-by-zero)."""
    mock_cfg.load_config.return_value = {}
    conn = _make_conn()

    _insert_tweet(conn, "org", "@ghost", _ts(1),
                  likes=0, replies=0, reposts=0, quotes=0, bookmarks=0)

    results = compute_amplifiers("org", window_days=30, conn=conn)
    assert len(results) == 1
    assert results[0].rpr == 0.0
    assert results[0].rt_v == 0.0
    assert results[0].qtr == 0.0


@patch("sable.pulse.meta.amplifiers.sable_cfg")
def test_window_filters_old_tweets(mock_cfg):
    """Tweets outside the window are excluded."""
    mock_cfg.load_config.return_value = {}
    conn = _make_conn()

    # Recent tweet (within 30d window)
    _insert_tweet(conn, "org", "@recent", _ts(5),
                  likes=10, replies=5, reposts=3, quotes=1, bookmarks=0)
    # Old tweet (200 days ago — outside window)
    _insert_tweet(conn, "org", "@old", _ts(200),
                  likes=100, replies=50, reposts=30, quotes=10, bookmarks=5)

    results = compute_amplifiers("org", window_days=30, conn=conn)
    authors = [r.author for r in results]
    assert "@recent" in authors
    assert "@old" not in authors


@patch("sable.pulse.meta.amplifiers.sable_cfg")
def test_empty_org_returns_empty(mock_cfg):
    """Org with no tweets returns empty list."""
    mock_cfg.load_config.return_value = {}
    conn = _make_conn()
    results = compute_amplifiers("nonexistent", window_days=30, conn=conn)
    assert results == []


@patch("sable.pulse.meta.amplifiers.sable_cfg")
def test_custom_weights_via_config(mock_cfg):
    """Config-provided weights are used instead of defaults."""
    mock_cfg.load_config.return_value = {
        "pulse_meta": {
            "amplifier_weights": {"rt_v": 0.0, "rpr": 0.0, "qtr": 1.0}
        }
    }
    conn = _make_conn()

    # Author A: high quotes only
    _insert_tweet(conn, "org", "@quoter", _ts(1),
                  likes=0, replies=0, reposts=0, quotes=100, bookmarks=0)
    # Author B: high reposts only
    _insert_tweet(conn, "org", "@retweeter", _ts(1),
                  likes=0, replies=0, reposts=100, quotes=0, bookmarks=0)

    results = compute_amplifiers("org", window_days=30, conn=conn)
    assert results[0].author == "@quoter"  # QTR weighted 100%


def test_weight_sum():
    """Default weights sum to 1.0."""
    assert abs((W_RT_V + W_RPR + W_QTR) - 1.0) < 1e-9


@patch("sable.pulse.meta.amplifiers.sable_cfg")
def test_multiple_days_active_affects_rt_v(mock_cfg):
    """Author posting across 5 distinct days has lower RT_v than one posting on 1 day."""
    mock_cfg.load_config.return_value = {}
    conn = _make_conn()

    # Author A: 50 reposts across 5 distinct days → RT_v = 10
    for i in range(5):
        _insert_tweet(conn, "org", "@spread", _ts(i),
                      likes=0, replies=0, reposts=10, quotes=0, bookmarks=0)
    # Author B: 50 reposts on 1 day → RT_v = 50
    for _ in range(5):
        _insert_tweet(conn, "org", "@burst", _ts(0),
                      likes=0, replies=0, reposts=10, quotes=0, bookmarks=0)

    results = compute_amplifiers("org", window_days=30, conn=conn)
    by_author = {r.author: r for r in results}
    assert by_author["@burst"].rt_v > by_author["@spread"].rt_v
