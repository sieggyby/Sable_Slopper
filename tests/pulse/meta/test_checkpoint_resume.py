"""Tests for scan checkpoint/resume functionality."""
from __future__ import annotations

import os
import importlib

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _make_db(tmp_path):
    """Return a fresh meta_db module pointed at tmp SQLite."""
    os.environ["SABLE_HOME"] = str(tmp_path)
    import sable.shared.paths as _paths
    import sable.pulse.meta.db as _db
    importlib.reload(_paths)
    importlib.reload(_db)
    return _db


def _fake_tweet(tweet_id: str, handle: str) -> dict:
    return {
        "id_str": tweet_id,
        "full_text": f"tweet {tweet_id}",
        "created_at": "Mon Mar 20 12:00:00 +0000 2026",
        "favorite_count": 10,
        "reply_count": 2,
        "retweet_count": 3,
        "quote_count": 0,
        "bookmark_count": 0,
        "views_count": 100,
        "user": {"screen_name": handle.lstrip("@"), "followers_count": 1000},
    }


def test_checkpoint_author_and_get_completed(tmp_path, monkeypatch):
    """checkpoint_author stores handle, get_completed_authors returns it."""
    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    db = _make_db(tmp_path)
    db.migrate()

    scan_id = db.create_scan_run("test_org", mode="incremental")

    assert db.get_completed_authors(scan_id) == set()

    db.checkpoint_author(scan_id, "@alice", tweets_collected=5)
    db.checkpoint_author(scan_id, "@bob", tweets_collected=3)

    completed = db.get_completed_authors(scan_id)
    assert completed == {"@alice", "@bob"}


def test_checkpoint_is_per_scan(tmp_path, monkeypatch):
    """Checkpoints from scan 1 don't bleed into scan 2."""
    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    db = _make_db(tmp_path)
    db.migrate()

    scan1 = db.create_scan_run("test_org", mode="incremental")
    scan2 = db.create_scan_run("test_org", mode="incremental")

    db.checkpoint_author(scan1, "@alice")
    db.checkpoint_author(scan2, "@bob")

    assert db.get_completed_authors(scan1) == {"@alice"}
    assert db.get_completed_authors(scan2) == {"@bob"}


def test_scanner_skips_checkpointed_authors(tmp_path, monkeypatch):
    """Scanner.run() skips authors already in scan_checkpoints."""
    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    db = _make_db(tmp_path)
    db.migrate()

    scan_id = db.create_scan_run("test_org", mode="incremental")

    # Pre-checkpoint alice
    db.checkpoint_author(scan_id, "@alice", tweets_collected=5)

    from sable.pulse.meta.scanner import Scanner

    scanner = Scanner(
        org="test_org",
        watchlist=[{"handle": "@alice"}, {"handle": "@bob"}],
        db=db,
        max_cost=10.0,
    )

    # Only bob should be fetched
    fetched_handles = []

    async def mock_fetch(handle, since_id=None, limit=100, lookback_hours=48, max_requests=32):
        fetched_handles.append(handle)
        return [], 1

    monkeypatch.setattr("sable.pulse.meta.scanner._fetch_author_tweets_async", mock_fetch)

    scanner.run(scan_id=scan_id)

    # alice was checkpointed — should NOT be fetched
    assert "@alice" not in fetched_handles and "alice" not in fetched_handles
    # bob should be fetched
    assert any("bob" in h for h in fetched_handles)


def test_scanner_checkpoints_each_author(tmp_path, monkeypatch):
    """After processing an author, scanner writes a checkpoint."""
    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    db = _make_db(tmp_path)
    db.migrate()

    scan_id = db.create_scan_run("test_org", mode="incremental")

    from sable.pulse.meta.scanner import Scanner

    scanner = Scanner(
        org="test_org",
        watchlist=[{"handle": "@alice"}],
        db=db,
        max_cost=10.0,
    )

    async def mock_fetch(handle, since_id=None, limit=100, lookback_hours=48, max_requests=32):
        return [_fake_tweet("100", "@alice")], 1

    monkeypatch.setattr("sable.pulse.meta.scanner._fetch_author_tweets_async", mock_fetch)
    monkeypatch.setattr("sable.pulse.meta.fingerprint.classify_tweet", lambda t: ("thread", []))

    mock_norm = MagicMock()
    for attr in ("author_median_likes", "author_median_replies", "author_median_reposts",
                 "author_median_quotes", "author_median_total", "author_median_same_format",
                 "likes_lift", "replies_lift", "reposts_lift", "quotes_lift",
                 "total_lift", "format_lift"):
        setattr(mock_norm, attr, 1.0)
    mock_norm.format_lift_reliable = False
    mock_norm.author_quality.grade = "adequate"
    mock_norm.author_quality.weight = 0.5
    monkeypatch.setattr("sable.pulse.meta.normalize.compute_author_lift", lambda t, h: mock_norm)

    scanner.run(scan_id=scan_id)

    completed = db.get_completed_authors(scan_id)
    assert "@alice" in completed


def test_checkpoint_idempotent(tmp_path, monkeypatch):
    """Calling checkpoint_author twice for same scan+handle doesn't error."""
    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    db = _make_db(tmp_path)
    db.migrate()

    scan_id = db.create_scan_run("test_org", mode="incremental")

    db.checkpoint_author(scan_id, "@alice", tweets_collected=3)
    db.checkpoint_author(scan_id, "@alice", tweets_collected=5)  # Should update, not error

    completed = db.get_completed_authors(scan_id)
    assert "@alice" in completed
