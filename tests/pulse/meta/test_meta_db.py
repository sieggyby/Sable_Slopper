"""Tests for sable.pulse.meta.db — T2-1: core query layer coverage."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest

from sable.pulse.meta.db import (
    _SCHEMA,
    SCHEMA_VERSION,
    bulk_upsert_tweets,
    checkpoint_author,
    complete_scan_run,
    create_scan_run,
    get_author_tweets,
    get_completed_authors,
    get_format_baselines,
    get_high_lift_tweets,
    upsert_author_profile,
    get_author_profile,
    insert_format_baseline,
    upsert_tweet,
)


def _make_db(tmp_path):
    """Create a meta.db at tmp_path and return the path."""
    db_path = tmp_path / "meta.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()
    conn.close()
    return db_path


def _make_tweet(tweet_id, handle="@alice", org="testorg", total_lift=1.8,
                format_bucket="standalone_text", posted_at="2026-03-17"):
    return {
        "tweet_id": tweet_id, "author_handle": handle, "text": f"tweet {tweet_id}",
        "posted_at": posted_at, "format_bucket": format_bucket, "attributes": [],
        "likes": 10, "replies": 2, "reposts": 3, "quotes": 1,
        "bookmarks": 0, "video_views": 0, "video_duration": None,
        "is_quote_tweet": False, "is_thread": False, "thread_length": 1,
        "has_image": False, "has_video": False, "has_link": False,
        "author_followers": 500,
        "author_median_likes": 5.0, "author_median_replies": 1.0,
        "author_median_reposts": 2.0, "author_median_quotes": 0.0,
        "author_median_total": 8.0, "author_median_same_format": 7.0,
        "likes_lift": 2.0, "replies_lift": 2.0, "reposts_lift": 1.5,
        "quotes_lift": 1.0, "total_lift": total_lift, "format_lift": 1.5,
        "author_quality_grade": "A", "author_quality_weight": 1.0,
        "format_lift_reliable": True, "scan_id": 1, "org": org,
    }


# ---------------------------------------------------------------------------
# 1. migrate creates all tables
# ---------------------------------------------------------------------------

def test_migrate_creates_all_tables(tmp_path):
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    expected = {
        "schema_version", "scanned_tweets", "author_profiles", "scan_runs",
        "format_baselines", "topic_signals", "hook_pattern_cache",
        "viral_anatomies", "lexicon_terms", "scan_checkpoints", "author_cadence",
    }
    assert expected.issubset(tables), f"Missing: {expected - tables}"


# ---------------------------------------------------------------------------
# 2. schema version
# ---------------------------------------------------------------------------

def test_migrate_sets_schema_version(tmp_path):
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    conn.close()
    assert row[0] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 3. upsert_tweet insert and idempotency
# ---------------------------------------------------------------------------

def test_upsert_tweet_insert_and_update(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        t = _make_tweet("t1")
        assert upsert_tweet(t) is True
        # Second insert returns False (duplicate)
        assert upsert_tweet(t) is False

    # Verify row exists
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM scanned_tweets WHERE tweet_id = 't1'").fetchone()
    conn.close()
    assert row is not None
    assert row["author_handle"] == "@alice"


# ---------------------------------------------------------------------------
# 4. attributes dict serialized as JSON
# ---------------------------------------------------------------------------

def test_upsert_tweet_attrs_dict_serialized(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        t = _make_tweet("t_dict_attrs")
        t["attributes"] = {"type": "thread", "tag": "alpha"}
        upsert_tweet(t)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT attributes_json FROM scanned_tweets WHERE tweet_id = 't_dict_attrs'").fetchone()
    conn.close()
    parsed = json.loads(row["attributes_json"])
    assert isinstance(parsed, dict)
    assert parsed["type"] == "thread"


# ---------------------------------------------------------------------------
# 5. bulk_upsert_tweets
# ---------------------------------------------------------------------------

def test_bulk_upsert_tweets_returns_new_count(tmp_path):
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)

    tweets = [_make_tweet(f"bulk_{i}") for i in range(3)]
    with conn:
        count = bulk_upsert_tweets(conn, tweets)
    assert count == 3

    # Re-insert same tweets
    with conn:
        count2 = bulk_upsert_tweets(conn, tweets)
    assert count2 == 0
    conn.close()


# ---------------------------------------------------------------------------
# 6. get_author_tweets ordering
# ---------------------------------------------------------------------------

def test_get_author_tweets_ordering(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        for i in range(5):
            t = _make_tweet(f"ord_{i}", posted_at=f"2026-03-{10+i:02d}")
            upsert_tweet(t)
        result = get_author_tweets("@alice", "testorg")

    # Should be descending by posted_at
    dates = [r["posted_at"] for r in result]
    assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# 7. get_author_tweets limit
# ---------------------------------------------------------------------------

def test_get_author_tweets_limit(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        for i in range(10):
            upsert_tweet(_make_tweet(f"lim_{i}", posted_at=f"2026-03-{10+i:02d}"))
        result = get_author_tweets("@alice", "testorg", limit=5)
    assert len(result) == 5


# ---------------------------------------------------------------------------
# 8. get_high_lift_tweets threshold
# ---------------------------------------------------------------------------

def test_get_high_lift_tweets_threshold(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        upsert_tweet(_make_tweet("lo", total_lift=1.0))
        upsert_tweet(_make_tweet("mid", total_lift=2.0))
        upsert_tweet(_make_tweet("hi", total_lift=3.0))
        result = get_high_lift_tweets("testorg", "standalone_text", lift_threshold=2.5, days=30)
    assert len(result) == 1
    assert result[0]["tweet_id"] == "hi"


# ---------------------------------------------------------------------------
# 9. insert_format_baseline and get
# ---------------------------------------------------------------------------

def test_insert_format_baseline_and_get(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        insert_format_baseline("testorg", "thread", 7, 2.5, 20, 8)
        result = get_format_baselines("testorg", "thread", 7)
    assert len(result) == 1
    assert result[0]["avg_total_lift"] == 2.5
    assert result[0]["sample_count"] == 20
    assert result[0]["unique_authors"] == 8


# ---------------------------------------------------------------------------
# 9b. insert_format_baseline same-second dedup
# ---------------------------------------------------------------------------

def test_insert_format_baseline_same_second_dedup(tmp_path):
    """Calling insert_format_baseline twice in the same second replaces, not appends."""
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        insert_format_baseline("testorg", "thread", 7, 2.5, 20, 8)
        insert_format_baseline("testorg", "thread", 7, 3.0, 25, 10)
        result = get_format_baselines("testorg", "thread", 7)
    # Should have 1 row (second call replaced the first), not 2
    assert len(result) == 1
    assert result[0]["avg_total_lift"] == 3.0
    assert result[0]["sample_count"] == 25


# ---------------------------------------------------------------------------
# 10. get_format_baselines empty
# ---------------------------------------------------------------------------

def test_get_format_baselines_empty(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        result = get_format_baselines("testorg", "thread", 7)
    assert result == []


# ---------------------------------------------------------------------------
# 11. get_scan_runs
# ---------------------------------------------------------------------------

def test_get_scan_runs(tmp_path):
    from sable.pulse.meta.db import get_scan_runs
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        sid = create_scan_run("testorg", "full", watchlist_size=10)
        runs = get_scan_runs("testorg")
    assert len(runs) == 1
    assert runs[0]["id"] == sid
    assert runs[0]["org"] == "testorg"


# ---------------------------------------------------------------------------
# 12. upsert_author_profile
# ---------------------------------------------------------------------------

def test_upsert_author_profile(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        upsert_author_profile("@bob", "testorg", "t100", 50, "2026-03-20")
        p = get_author_profile("@bob", "testorg")
        assert p is not None
        assert p["tweet_count"] == 50

        # Update
        upsert_author_profile("@bob", "testorg", "t200", 75, "2026-03-21")
        p2 = get_author_profile("@bob", "testorg")
        assert p2["tweet_count"] == 75
        assert p2["last_tweet_id"] == "t200"


# ---------------------------------------------------------------------------
# 13. create_scan_run and complete
# ---------------------------------------------------------------------------

def test_create_scan_run_and_complete(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        sid = create_scan_run("testorg", "full")
        assert isinstance(sid, int)

        complete_scan_run(sid, tweets_collected=100, tweets_new=42, estimated_cost=0.2)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM scan_runs WHERE id = ?", (sid,)).fetchone()
    conn.close()
    assert row["completed_at"] is not None
    assert row["tweets_collected"] == 100
    assert row["tweets_new"] == 42


# ---------------------------------------------------------------------------
# 14. checkpoint and get_completed_authors
# ---------------------------------------------------------------------------

def test_checkpoint_author_and_get_completed(tmp_path):
    db_path = _make_db(tmp_path)
    with patch("sable.pulse.meta.db.meta_db_path", return_value=db_path):
        checkpoint_author(1, "@alice", 10)
        checkpoint_author(1, "@bob", 20)
        checkpoint_author(1, "@charlie", 5)
        completed = get_completed_authors(1)
    assert completed == {"@alice", "@bob", "@charlie"}
