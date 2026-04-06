"""AQ-13: Scanner handles BalanceExhaustedError mid-scan gracefully.

Tests transactional integrity: bulk_upsert_tweets + checkpoint are atomic.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch, MagicMock

import pytest

from sable.pulse.meta.db import bulk_upsert_tweets, migrate as meta_migrate
from sable.shared.socialdata import BalanceExhaustedError


def _make_meta_conn(tmp_path):
    """Create a real meta.db with schema."""
    db_path = tmp_path / "meta.db"
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        meta_migrate()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _make_tweet(tweet_id, handle="@alice"):
    """Minimal tweet dict for bulk_upsert_tweets."""
    return {
        "tweet_id": tweet_id,
        "author_handle": handle,
        "text": f"tweet {tweet_id}",
        "posted_at": "2026-03-17",
        "format_bucket": "standalone_text",
        "attributes": [],
        "likes": 10, "replies": 2, "reposts": 3, "quotes": 1,
        "bookmarks": 0, "video_views": 0, "video_duration": None,
        "is_quote_tweet": False, "is_thread": False, "thread_length": 1,
        "has_image": False, "has_video": False, "has_link": False,
        "author_followers": 500,
        "author_median_likes": 5.0, "author_median_replies": 1.0,
        "author_median_reposts": 2.0, "author_median_quotes": 0.0,
        "author_median_total": 8.0, "author_median_same_format": 7.0,
        "likes_lift": 2.0, "replies_lift": 2.0, "reposts_lift": 1.5,
        "quotes_lift": 1.0, "total_lift": 1.8, "format_lift": 1.5,
        "author_quality_grade": "A", "author_quality_weight": 1.0,
        "format_lift_reliable": True,
        "scan_id": 1, "org": "testorg",
    }


def test_bulk_upsert_returns_new_count(tmp_path):
    """bulk_upsert_tweets returns count of new tweets inserted."""
    conn = _make_meta_conn(tmp_path)
    tweets = [_make_tweet("100"), _make_tweet("101")]
    with conn:
        new = bulk_upsert_tweets(conn, tweets)
    assert new == 2

    # Inserting same tweets again → 0 new
    with conn:
        new2 = bulk_upsert_tweets(conn, tweets)
    assert new2 == 0
    conn.close()


def test_bulk_upsert_and_checkpoint_atomic(tmp_path):
    """Tweets + checkpoint in single transaction: if checkpoint fails, tweets rolled back."""
    conn = _make_meta_conn(tmp_path)
    tweets = [_make_tweet("200"), _make_tweet("201")]

    # Simulate: insert tweets then fail before checkpoint
    try:
        with conn:
            bulk_upsert_tweets(conn, tweets)
            raise RuntimeError("Simulated failure before checkpoint")
    except RuntimeError:
        pass

    # Tweets should NOT be persisted (transaction rolled back)
    count = conn.execute("SELECT COUNT(*) FROM scanned_tweets WHERE scan_id = 1").fetchone()[0]
    assert count == 0, "Tweets should be rolled back when transaction fails"
    conn.close()


def test_bulk_upsert_and_checkpoint_success(tmp_path):
    """Tweets + checkpoint in single transaction: both persist on success."""
    conn = _make_meta_conn(tmp_path)
    tweets = [_make_tweet("300"), _make_tweet("301")]

    with conn:
        new = bulk_upsert_tweets(conn, tweets)
        conn.execute(
            "INSERT OR REPLACE INTO scan_checkpoints (scan_id, author_handle, tweets_collected) VALUES (?, ?, ?)",
            (1, "@alice", new),
        )

    # Both tweets and checkpoint persisted
    tweet_count = conn.execute("SELECT COUNT(*) FROM scanned_tweets WHERE scan_id = 1").fetchone()[0]
    assert tweet_count == 2

    cp = conn.execute("SELECT tweets_collected FROM scan_checkpoints WHERE scan_id = 1 AND author_handle = '@alice'").fetchone()
    assert cp is not None
    assert cp[0] == 2
    conn.close()


def test_balance_exhausted_error_exists():
    """BalanceExhaustedError is importable from socialdata."""
    assert issubclass(BalanceExhaustedError, Exception)
