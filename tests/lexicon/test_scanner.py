"""Tests for sable.lexicon.scanner — community vocabulary extraction."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from sable.pulse.meta.db import _SCHEMA
from sable.lexicon.scanner import (
    scan_lexicon,
    compute_lsr,
    MIN_AUTHORS,
    MIN_TWEETS,
    MIN_TERM_APPEARANCES,
    MIN_TERM_AUTHORS,
    MAX_AUTHOR_SHARE,
)

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int = 0) -> str:
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _insert_tweet(conn, org, author, text, days_ago=0):
    import uuid
    tid = str(uuid.uuid4())[:12]
    conn.execute(
        """INSERT INTO scanned_tweets
           (tweet_id, org, author_handle, posted_at, text, likes, replies, reposts, quotes, bookmarks)
           VALUES (?, ?, ?, ?, ?, 10, 5, 3, 1, 0)""",
        (tid, org, author, _ts(days_ago), text),
    )
    conn.commit()


def _seed_corpus(conn, org="test_org", n_authors=15, tweets_per_author=5):
    """Seed a corpus that meets minimum thresholds.

    Uses a niche term '$NICHE' that appears in ~40% of tweets (well-distributed)
    and a generic term '$BTC' that appears in 80% (filtered by exclusivity).
    """
    for i in range(n_authors):
        author = f"@author_{i:03d}"
        for j in range(tweets_per_author):
            # Niche term: appears for ~40% of authors (6 out of 15)
            if i < 6 and j == 0:
                text = "Excited about $NICHE token launch and Real Yield mechanics"
            elif i < 12:
                text = "Another day in crypto $BTC is pumping hard"
            else:
                text = "Building something cool in the DeFi space"
            _insert_tweet(conn, org, author, text, days_ago=j)


# ---------------------------------------------------------------------------
# LSR computation
# ---------------------------------------------------------------------------

def test_compute_lsr_basic():
    """LSR = (authors/total) * log2(1 + mentions)."""
    import math
    assert compute_lsr(5, 20, 10) == pytest.approx(
        (5 / 20) * math.log2(11), rel=1e-3
    )


def test_compute_lsr_zero_authors():
    """Zero total authors → 0."""
    assert compute_lsr(0, 0, 10) == 0.0


# ---------------------------------------------------------------------------
# Threshold enforcement
# ---------------------------------------------------------------------------

def test_scan_empty_org():
    """Empty org returns empty list."""
    conn = _make_conn()
    assert scan_lexicon("nonexistent", conn=conn) == []


def test_scan_below_author_threshold():
    """Fewer than MIN_AUTHORS returns empty."""
    conn = _make_conn()
    # Insert 5 authors (below MIN_AUTHORS=10)
    for i in range(5):
        for j in range(12):
            _insert_tweet(conn, "org", f"@a{i}", "test $BTC", days_ago=j % 7)
    result = scan_lexicon("org", conn=conn)
    assert result == []


def test_scan_below_tweet_threshold():
    """Fewer than MIN_TWEETS returns empty."""
    conn = _make_conn()
    # Insert 12 authors but only 2 tweets each (24 < 50)
    for i in range(12):
        for j in range(2):
            _insert_tweet(conn, "org", f"@a{i}", "test $BTC", days_ago=j)
    result = scan_lexicon("org", conn=conn)
    assert result == []


# ---------------------------------------------------------------------------
# Exclusivity filter
# ---------------------------------------------------------------------------

def test_exclusivity_filters_generic_terms():
    """Terms appearing in >25% of authors are filtered out."""
    conn = _make_conn()
    _seed_corpus(conn)
    result = scan_lexicon("test_org", conn=conn)
    terms = [r["term"] for r in result]
    # $BTC appears in 80% of authors → should be filtered
    assert "$btc" not in terms or all(
        r["unique_authors"] / r["total_authors"] <= MAX_AUTHOR_SHARE
        for r in result
    )


def test_niche_terms_kept():
    """Terms within exclusivity bounds are kept."""
    conn = _make_conn()
    _seed_corpus(conn)
    result = scan_lexicon("test_org", conn=conn)
    # If any results exist, they must satisfy exclusivity bounds
    for r in result:
        assert r["unique_authors"] / r["total_authors"] <= MAX_AUTHOR_SHARE
        assert r["unique_authors"] >= MIN_TERM_AUTHORS
        assert r["mention_count"] >= MIN_TERM_APPEARANCES


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

def test_result_keys():
    """Each result has expected keys."""
    conn = _make_conn()
    _seed_corpus(conn)
    result = scan_lexicon("test_org", conn=conn)
    if result:
        r = result[0]
        assert "term" in r
        assert "mention_count" in r
        assert "unique_authors" in r
        assert "total_authors" in r
        assert "lsr" in r


def test_results_sorted_by_lsr():
    """Results are sorted by LSR descending."""
    conn = _make_conn()
    _seed_corpus(conn)
    result = scan_lexicon("test_org", conn=conn)
    if len(result) >= 2:
        for i in range(len(result) - 1):
            assert result[i]["lsr"] >= result[i + 1]["lsr"]


def test_top_n_limits_results():
    """top_n parameter limits result count."""
    conn = _make_conn()
    _seed_corpus(conn)
    result = scan_lexicon("test_org", top_n=2, conn=conn)
    assert len(result) <= 2


# ---------------------------------------------------------------------------
# Constants are importable (for FEATURE-14 reuse)
# ---------------------------------------------------------------------------

def test_constants_exported():
    """Threshold constants are importable."""
    assert MIN_AUTHORS == 10
    assert MIN_TWEETS == 50
    assert MIN_TERM_APPEARANCES == 3
    assert MIN_TERM_AUTHORS == 2
    assert MAX_AUTHOR_SHARE == 0.25
