"""Tests for Scanner per-phase cost breakdown."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


def _make_scanner(monkeypatch, watchlist, deep=False):
    """Build a Scanner with mocked DB and SocialData."""
    from sable.pulse.meta.scanner import Scanner

    db = MagicMock()
    db.get_author_profile.return_value = None
    db.get_author_tweets.return_value = []
    db.upsert_tweet.return_value = True
    db.upsert_author_profile.return_value = None

    scanner = Scanner(
        org="test_org",
        watchlist=watchlist,
        db=db,
        deep=deep,
        max_cost=10.0,
    )
    return scanner


def _mock_fetch(tweets_by_handle):
    """Return an async function that returns (tweets, request_count)."""
    async def _fetch(handle, since_id=None, limit=100, lookback_hours=48, max_requests=32):
        from sable.shared.handles import strip_handle
        tweets = tweets_by_handle.get(strip_handle(handle), [])
        return tweets, 1
    return _fetch


def _raw_tweet(tweet_id="1", handle="testuser"):
    return {
        "id_str": tweet_id,
        "full_text": "gm",
        "created_at": "Thu Mar 17 12:00:00 +0000 2026",
        "user": {"screen_name": handle, "followers_count": 500},
        "favorite_count": 10,
        "reply_count": 2,
        "retweet_count": 3,
        "quote_count": 0,
        "bookmark_count": 1,
        "views_count": 200,
    }


def test_cost_breakdown_fetch_only(monkeypatch):
    """Non-deep scan tracks all cost under 'fetch' phase."""
    monkeypatch.setattr(
        "sable.pulse.meta.scanner._fetch_author_tweets_async",
        _mock_fetch({"alice": [_raw_tweet("1", "alice")], "bob": [_raw_tweet("2", "bob")]}),
    )
    monkeypatch.setattr(
        "sable.pulse.meta.fingerprint.classify_tweet",
        lambda t: ("thread", {}),
    )
    # Mock compute_author_lift to return an object with the attrs the scanner reads
    mock_norm = MagicMock()
    mock_norm.author_median_likes = 0
    mock_norm.author_median_replies = 0
    mock_norm.author_median_reposts = 0
    mock_norm.author_median_quotes = 0
    mock_norm.author_median_total = 0
    mock_norm.author_median_same_format = 0
    mock_norm.likes_lift = 1.0
    mock_norm.replies_lift = 1.0
    mock_norm.reposts_lift = 1.0
    mock_norm.quotes_lift = 1.0
    mock_norm.total_lift = 1.0
    mock_norm.format_lift = 1.0
    mock_norm.format_lift_reliable = False
    mock_norm.author_quality.grade = "adequate"
    mock_norm.author_quality.weight = 0.5
    monkeypatch.setattr("sable.pulse.meta.normalize.compute_author_lift", lambda t, h: mock_norm)

    scanner = _make_scanner(monkeypatch, [
        {"handle": "@alice"},
        {"handle": "@bob"},
    ])
    result = scanner.run(scan_id=1)

    assert result["cost_breakdown"]["fetch"] == pytest.approx(0.004)
    assert result["cost_breakdown"]["deep_search"] == 0.0
    assert result["estimated_cost"] == pytest.approx(0.004)


def test_cost_breakdown_with_deep_mode(monkeypatch):
    """Deep scan tracks fetch + deep_search phases separately."""
    monkeypatch.setattr(
        "sable.pulse.meta.scanner._fetch_author_tweets_async",
        _mock_fetch({"alice": []}),
    )

    async def _mock_search(query, limit=50):
        return []

    monkeypatch.setattr("sable.pulse.meta.scanner._search_tweets_async", _mock_search)

    scanner = _make_scanner(monkeypatch, [{"handle": "@alice"}], deep=True)
    result = scanner.run(scan_id=1)

    assert result["cost_breakdown"]["fetch"] == pytest.approx(0.002)
    assert result["cost_breakdown"]["deep_search"] == pytest.approx(0.006)  # 3 queries


def test_cost_breakdown_present_in_result_keys(monkeypatch):
    """cost_breakdown key always present in scan result."""
    monkeypatch.setattr(
        "sable.pulse.meta.scanner._fetch_author_tweets_async",
        _mock_fetch({}),
    )

    scanner = _make_scanner(monkeypatch, [{"handle": "@alice"}])
    result = scanner.run(scan_id=1)

    assert "cost_breakdown" in result
    assert "fetch" in result["cost_breakdown"]
    assert "deep_search" in result["cost_breakdown"]
