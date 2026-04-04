"""Tests for cursor cycling pagination in _fetch_author_tweets_async."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def _raw_tweet(tweet_id: str, date: str = "Mon Mar 20 12:00:00 +0000 2026") -> dict:
    return {
        "id_str": tweet_id,
        "full_text": f"tweet {tweet_id}",
        "created_at": date,
        "favorite_count": 10,
        "reply_count": 2,
        "retweet_count": 3,
        "quote_count": 0,
        "bookmark_count": 0,
        "views_count": 100,
        "user": {"screen_name": "alice", "followers_count": 1000},
    }


def test_single_page_returns_all_tweets():
    """Single page with no next_cursor returns all tweets."""
    from sable.pulse.meta.scanner import _fetch_author_tweets_async

    mock_response = {
        "tweets": [_raw_tweet("100"), _raw_tweet("99")],
    }

    with patch("sable.pulse.meta.scanner.socialdata_get_async",
               new=AsyncMock(return_value=mock_response)):
        tweets, count = asyncio.run(_fetch_author_tweets_async("alice", lookback_hours=9999))

    assert len(tweets) == 2
    assert count == 1


def test_cursor_cycling_fetches_multiple_pages():
    """When next_cursor is present, fetches additional pages."""
    from sable.pulse.meta.scanner import _fetch_author_tweets_async

    page1 = {
        "tweets": [_raw_tweet("100"), _raw_tweet("99")],
        "next_cursor": "cursor_page2",
    }
    page2 = {
        "tweets": [_raw_tweet("98"), _raw_tweet("97")],
        # No next_cursor — last page
    }

    mock_api = AsyncMock(side_effect=[page1, page2])

    with patch("sable.pulse.meta.scanner.socialdata_get_async", new=mock_api):
        tweets, count = asyncio.run(_fetch_author_tweets_async("alice", lookback_hours=9999))

    assert len(tweets) == 4
    assert count == 2
    # Second call should include cursor param
    assert mock_api.call_args_list[1][1].get("params", {}).get("cursor") == "cursor_page2" or \
           "cursor" in str(mock_api.call_args_list[1])


def test_cursor_cycling_stops_at_since_id():
    """Pagination stops when since_id is reached."""
    from sable.pulse.meta.scanner import _fetch_author_tweets_async

    page1 = {
        "tweets": [_raw_tweet("100"), _raw_tweet("99")],
        "next_cursor": "cursor2",
    }
    page2 = {
        "tweets": [_raw_tweet("50"), _raw_tweet("49")],  # Below since_id=80
        "next_cursor": "cursor3",  # Should not be followed
    }

    mock_api = AsyncMock(side_effect=[page1, page2])

    with patch("sable.pulse.meta.scanner.socialdata_get_async", new=mock_api):
        tweets, count = asyncio.run(
            _fetch_author_tweets_async("alice", since_id="80", lookback_hours=9999)
        )

    # Should have tweets 100 and 99 from page1, 50 and 49 are <= since_id=80
    assert all(int(t["id_str"]) > 80 for t in tweets)
    assert count == 2  # Fetched 2 pages, stopped after page2 hit since_id


def test_cursor_cycling_deduplicates():
    """Duplicate tweet IDs across pages are deduplicated."""
    from sable.pulse.meta.scanner import _fetch_author_tweets_async

    page1 = {
        "tweets": [_raw_tweet("100"), _raw_tweet("99")],
        "next_cursor": "cursor2",
    }
    page2 = {
        "tweets": [_raw_tweet("100"), _raw_tweet("98")],  # 100 is duplicate
    }

    mock_api = AsyncMock(side_effect=[page1, page2])

    with patch("sable.pulse.meta.scanner.socialdata_get_async", new=mock_api):
        tweets, count = asyncio.run(_fetch_author_tweets_async("alice", lookback_hours=9999))

    ids = [t["id_str"] for t in tweets]
    assert len(ids) == len(set(ids)), "Duplicate tweet IDs should be removed"
    assert len(tweets) == 3


def test_cursor_cycling_respects_max_pages():
    """Pagination stops at _MAX_TWEET_PAGES."""
    from sable.pulse.meta.scanner import _fetch_author_tweets_async, _MAX_TWEET_PAGES

    # Each page returns tweets and another cursor forever
    mock_api = AsyncMock(return_value={
        "tweets": [_raw_tweet("100")],
        "next_cursor": "next",
    })

    with patch("sable.pulse.meta.scanner.socialdata_get_async", new=mock_api):
        tweets, count = asyncio.run(_fetch_author_tweets_async("alice", lookback_hours=9999))

    # Should stop after _MAX_TWEET_PAGES even though cursor keeps coming
    assert count == _MAX_TWEET_PAGES


def test_request_count_used_for_cost_tracking(monkeypatch):
    """Scanner uses request_count from _fetch_author_tweets_async for cost."""
    from sable.pulse.meta.scanner import Scanner
    from unittest.mock import MagicMock

    db = MagicMock()
    db.get_author_profile.return_value = None
    db.get_author_tweets.return_value = []
    db.upsert_tweet.return_value = True

    scanner = Scanner(
        org="test_org",
        watchlist=[{"handle": "@alice"}],
        db=db,
        max_cost=10.0,
    )

    # Mock fetch to return 3 pages worth of requests
    async def mock_fetch(handle, since_id=None, limit=100, lookback_hours=48, max_requests=32):
        return [], 3

    monkeypatch.setattr("sable.pulse.meta.scanner._fetch_author_tweets_async", mock_fetch)

    result = scanner.run(scan_id=1)

    # 3 requests × $0.002 = $0.006
    assert result["estimated_cost"] == pytest.approx(0.006)
    assert result["cost_breakdown"]["fetch"] == pytest.approx(0.006)
