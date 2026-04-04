"""Regression tests for Scanner budget-abort paths and dry-run DB hygiene."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_normalized(tweet_id="t1"):
    """Return a minimal AuthorNormalizedTweet with all required fields."""
    from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality
    return AuthorNormalizedTweet(
        tweet_id=tweet_id, author_handle="@alice", format_bucket="standalone_text",
        attributes=[], posted_at="2026-03-20T12:00:00+00:00", text="test tweet",
        likes=10, replies=2, reposts=3, quotes=1, bookmarks=0, video_views=0,
        author_followers=5000,
        author_median_likes=10.0, author_median_replies=2.0, author_median_reposts=3.0,
        author_median_quotes=1.0, author_median_total=16.0, author_median_same_format=16.0,
        likes_lift=1.0, replies_lift=1.0, reposts_lift=1.0, quotes_lift=1.0,
        total_lift=1.0, format_lift=1.0, format_lift_reliable=False,
        author_quality=AuthorQuality(grade="fallback", total_tweets=0, total_scans=0,
                                      reasons=[], weight=0.25),
    )


def _fake_tweet(tweet_id: str = "t1", handle: str = "@alice") -> dict:
    return {
        "id_str": tweet_id,
        "full_text": "test tweet",
        "created_at": "Mon Mar 20 12:00:00 +0000 2026",
        "favorite_count": 10,
        "reply_count": 2,
        "retweet_count": 3,
        "quote_count": 1,
        "bookmark_count": 0,
        "views_count": 0,
        "is_quote_status": False,
        "in_reply_to_screen_name": None,
        "user": {"screen_name": handle.lstrip("@"), "followers_count": 5000},
        "entities": {},
    }


def _make_db(tmp_path):
    """Return a fresh meta_db module pointed at a tmp SQLite file."""
    os.environ["SABLE_HOME"] = str(tmp_path)
    # Re-import to pick up new SABLE_HOME
    import importlib
    import sable.shared.paths as _paths
    import sable.pulse.meta.db as _db
    importlib.reload(_paths)
    importlib.reload(_db)
    return _db


def _make_scanner(watchlist, max_cost, db, deep=False):
    from sable.pulse.meta.scanner import Scanner
    return Scanner(
        org="test_org",
        watchlist=watchlist,
        db=db,
        cfg_meta={"lookback_hours": 48},
        deep=deep,
        full=True,  # skip cursor lookups
        dry_run=False,
        max_cost=max_cost,
    )


# ---------------------------------------------------------------------------
# Test 1: dry-run leaves no scan_runs row
# ---------------------------------------------------------------------------

def test_dry_run_leaves_no_scan_run_row(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    db.migrate()

    monkeypatch.setenv("SABLE_HOME", str(tmp_path))

    # Add a watchlist entry so the command doesn't bail early
    from sable.pulse.meta import watchlist as wl_mod
    import importlib
    import sable.shared.paths as _paths
    importlib.reload(_paths)
    importlib.reload(wl_mod)

    wl_mod.add_handle("@alice", org="test_org")

    from sable.pulse.meta.cli import meta_scan
    from sable import config as sable_cfg

    runner = CliRunner()

    with patch.object(sable_cfg, "load_config", return_value={"pulse_meta": {"max_cost_per_run": 1.0}}):
        runner.invoke(meta_scan, ["--org", "test_org", "--dry-run"])

    rows = db.get_scan_runs("test_org")
    assert rows == [], f"Expected no scan_runs rows after dry-run, got: {rows}"


# ---------------------------------------------------------------------------
# Test 2: watchlist budget abort preserves partial counts
# ---------------------------------------------------------------------------

def test_watchlist_budget_abort_preserves_partial_counts(tmp_path, monkeypatch):
    from sable.pulse.meta.scanner import _COST_PER_REQUEST

    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    db = _make_db(tmp_path)
    db.migrate()

    watchlist = [{"handle": "@alice"}, {"handle": "@bob"}]
    # Budget allows first account but not second
    max_cost = _COST_PER_REQUEST * 1.5
    scanner = _make_scanner(watchlist, max_cost, db)

    fake_tweets = [_fake_tweet("t1", "@alice")]

    with patch(
        "sable.pulse.meta.scanner._fetch_author_tweets_async",
        new=AsyncMock(return_value=(fake_tweets, 1)),
    ), patch(
        "sable.pulse.meta.fingerprint.classify_tweet",
        return_value=("standalone_text", []),
    ), patch(
        "sable.pulse.meta.normalize.compute_author_lift",
        return_value=_make_normalized("t1"),
    ):
        result = scanner.run(scan_id=1)

    assert result["aborted"] is True
    assert result["tweets_collected"] >= 1, "First account should have been processed"
    assert result["estimated_cost"] > 0


# ---------------------------------------------------------------------------
# Test 3: deep-mode budget abort
# ---------------------------------------------------------------------------

def test_deep_mode_budget_abort(tmp_path, monkeypatch):
    from sable.pulse.meta.scanner import _COST_PER_REQUEST

    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    db = _make_db(tmp_path)
    db.migrate()

    watchlist = [{"handle": "@alice"}, {"handle": "@bob"}]
    # Enough for both watchlist accounts but not a single deep-mode search
    max_cost = _COST_PER_REQUEST * (len(watchlist) + 0.5)
    scanner = _make_scanner(watchlist, max_cost, db, deep=True)

    with patch(
        "sable.pulse.meta.scanner._fetch_author_tweets_async",
        new=AsyncMock(return_value=([], 1)),
    ), patch(
        "sable.pulse.meta.scanner._search_tweets_async",
        new=AsyncMock(return_value=[]),
    ):
        result = scanner.run(scan_id=1)

    assert result["aborted"] is True
    # Cost must have exceeded the watchlist-phase cost (abort in deep phase)
    assert result["estimated_cost"] > _COST_PER_REQUEST * len(watchlist)


# ---------------------------------------------------------------------------
# Test 4: aborted scan records real partial counts (not fake zeros)
# ---------------------------------------------------------------------------

def test_aborted_scan_records_real_partial_counts(tmp_path, monkeypatch):
    from sable.pulse.meta.scanner import _COST_PER_REQUEST

    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    db = _make_db(tmp_path)
    db.migrate()

    watchlist = [{"handle": "@alice"}, {"handle": "@bob"}]
    max_cost = _COST_PER_REQUEST * 1.5
    scanner = _make_scanner(watchlist, max_cost, db)
    scan_id = db.create_scan_run("test_org", mode="incremental", watchlist_size=2)

    fake_tweets = [_fake_tweet("t1", "@alice")]

    with patch(
        "sable.pulse.meta.scanner._fetch_author_tweets_async",
        new=AsyncMock(return_value=(fake_tweets, 1)),
    ), patch(
        "sable.pulse.meta.fingerprint.classify_tweet",
        return_value=("standalone_text", []),
    ), patch(
        "sable.pulse.meta.normalize.compute_author_lift",
        return_value=_make_normalized("t1"),
    ):
        result = scanner.run(scan_id=scan_id)

    # Simulate what CLI now does on abort
    db.complete_scan_run(
        scan_id=scan_id,
        tweets_collected=result["tweets_collected"],
        tweets_new=result["tweets_new"],
        estimated_cost=result["estimated_cost"],
    )

    rows = db.get_scan_runs("test_org")
    assert rows, "Expected at least one scan_runs row"
    row = rows[0]
    assert row["tweets_collected"] >= 1, "Expected partial count, got 0"
    assert row["estimated_cost"] > 0, "Expected non-zero cost, got 0"


# ---------------------------------------------------------------------------
# Test T5: scanner exception recovers partial counts from DB before marking failed
# ---------------------------------------------------------------------------

def test_scanner_exception_marks_scan_run_failed(tmp_path, monkeypatch):
    """End-to-end: scanner raises mid-run, CLI recovery path reads partial counts and marks failed."""
    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    db = _make_db(tmp_path)
    db.migrate()

    scanner = _make_scanner(
        [{"handle": "@alice"}, {"handle": "@bob"}],
        max_cost=999,
        db=db,
    )

    # Return tweets for both authors; classify_tweet succeeds for t1, raises for t2
    classify_calls = {"n": 0}

    def _classify_side_effect(tweet):
        classify_calls["n"] += 1
        if classify_calls["n"] >= 2:
            raise RuntimeError("injected classify failure")
        return ("standalone_text", [])

    with patch(
        "sable.pulse.meta.scanner._fetch_author_tweets_async",
        new=AsyncMock(side_effect=[
            ([_fake_tweet("t1", "@alice")], 1),
            ([_fake_tweet("t2", "@bob")], 1),
        ]),
    ), patch(
        "sable.pulse.meta.fingerprint.classify_tweet",
        side_effect=_classify_side_effect,
    ), patch(
        "sable.pulse.meta.normalize.compute_author_lift",
        return_value=_make_normalized("t1"),
    ):
        scan_id = db.create_scan_run("test_org", mode="incremental", watchlist_size=2)
        try:
            scanner.run(scan_id)
        except Exception as e:
            partial = db.get_tweets_for_scan(scan_id, "test_org")
            db.fail_scan_run(scan_id, str(e), tweets_collected=len(partial))

    rows = db.get_scan_runs("test_org")
    assert rows, "Expected scan_runs row"
    row = rows[0]
    assert row["completed_at"] is not None, "completed_at should be set after fail_scan_run"
    assert row["claude_raw"] is not None, "claude_raw should be set"
    assert row["claude_raw"].startswith("FAILED:"), f"Expected FAILED: prefix, got: {row['claude_raw']}"
    assert row["tweets_collected"] >= 1, f"Expected partial count >= 1, got {row['tweets_collected']}"


# ---------------------------------------------------------------------------
# _parse_twitter_date — empty / None input
# ---------------------------------------------------------------------------

from sable.pulse.meta.scanner import _parse_twitter_date


def test_parse_twitter_date_empty_string_returns_none():
    assert _parse_twitter_date("") is None


def test_parse_twitter_date_none_returns_none():
    assert _parse_twitter_date(None) is None  # type: ignore[arg-type]
