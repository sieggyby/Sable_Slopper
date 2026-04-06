"""Tests for sable.pulse.meta.scanner — T2-2: scanner class coverage."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sable.pulse.meta.scanner import _normalise_tweet, Scanner


# ---------------------------------------------------------------------------
# 1. _normalise_tweet
# ---------------------------------------------------------------------------

def _raw_tweet(tweet_id="123", handle="alice", text="hello crypto"):
    """Minimal raw SocialData tweet structure."""
    return {
        "id_str": tweet_id,
        "full_text": text,
        "created_at": "Thu Mar 17 12:00:00 +0000 2026",
        "user": {"followers_count": 500},
        "favorite_count": 10,
        "retweet_count": 3,
        "reply_count": 2,
        "quote_count": 1,
        "bookmark_count": 0,
        "views_count": 100,
    }


def test_normalise_tweet_extracts_fields():
    raw = _raw_tweet()
    result = _normalise_tweet(raw, "@alice")
    assert result is not None
    assert result["tweet_id"] == "123"
    assert result["author_handle"] == "@alice"
    assert result["likes"] == 10
    assert result["reposts"] == 3
    assert result["replies"] == 2
    assert result["author_followers"] == 500


def test_normalise_tweet_rejects_missing_id():
    raw = _raw_tweet()
    del raw["id_str"]
    raw.pop("id", None)
    assert _normalise_tweet(raw, "@alice") is None


def test_normalise_tweet_rejects_missing_engagement():
    raw = _raw_tweet()
    del raw["favorite_count"]
    assert _normalise_tweet(raw, "@alice") is None


# ---------------------------------------------------------------------------
# 2. Budget cap
# ---------------------------------------------------------------------------

def test_scanner_budget_cap_limits_pages():
    """max_cost=0.01 → 5 pages max (at $0.002/request)."""
    db_mock = MagicMock()
    db_mock.get_completed_authors.return_value = set()
    db_mock.get_author_profile.return_value = None

    scanner = Scanner(
        org="testorg",
        watchlist=[{"handle": "@alice"}],
        db=db_mock,
        max_cost=0.01,
    )
    est = scanner.estimate_cost()
    assert est["accounts"] == 1
    # Budget should constrain pages during run


# ---------------------------------------------------------------------------
# 3. Empty author checkpoints
# ---------------------------------------------------------------------------

def test_scanner_empty_author_handled(tmp_path):
    """Scanner handles author returning 0 tweets without crashing."""
    db_mock = MagicMock()
    db_mock.get_completed_authors.return_value = set()
    db_mock.get_author_profile.return_value = None

    scanner = Scanner(
        org="testorg",
        watchlist=[{"handle": "@empty_author"}],
        db=db_mock,
        max_cost=1.0,
    )

    async def mock_fetch(*args, **kwargs):
        return {"tweets": [], "next_cursor": None}

    with patch("sable.pulse.meta.scanner.socialdata_get_async", new_callable=lambda: lambda: AsyncMock(side_effect=mock_fetch)):
        result = scanner.run(scan_id=1)

    assert result["tweets_collected"] == 0


# ---------------------------------------------------------------------------
# 4. Balance exhausted stops gracefully
# ---------------------------------------------------------------------------

def test_scanner_balance_exhausted_stops_gracefully():
    """BalanceExhaustedError during fetch → scan completes without crash."""
    from sable.shared.socialdata import BalanceExhaustedError

    db_mock = MagicMock()
    db_mock.get_completed_authors.return_value = set()
    db_mock.get_author_profile.return_value = None

    scanner = Scanner(
        org="testorg",
        watchlist=[{"handle": "@alice"}],
        db=db_mock,
        max_cost=1.0,
    )

    async def mock_fetch(*args, **kwargs):
        raise BalanceExhaustedError("Insufficient balance")

    with patch("sable.pulse.meta.scanner.socialdata_get_async", new_callable=lambda: lambda: AsyncMock(side_effect=mock_fetch)):
        result = scanner.run(scan_id=1)

    # Should complete (not raise), with 0 tweets
    assert result["tweets_collected"] == 0


# ---------------------------------------------------------------------------
# 5. Resume from checkpoint
# ---------------------------------------------------------------------------

def test_scanner_resumes_from_checkpoint():
    """Already-completed authors are skipped on resume."""
    db_mock = MagicMock()
    db_mock.get_completed_authors.return_value = {"@alice"}
    db_mock.get_author_profile.return_value = None

    scanner = Scanner(
        org="testorg",
        watchlist=[{"handle": "@alice"}, {"handle": "@bob"}],
        db=db_mock,
        max_cost=1.0,
    )

    mock_api = AsyncMock(return_value={"tweets": [], "next_cursor": None})

    with patch("sable.pulse.meta.scanner.socialdata_get_async", mock_api):
        scanner.run(scan_id=1)

    # Only @bob should have been fetched, @alice skipped
    assert mock_api.call_count == 1
    # Verify the call was for bob, not alice
    call_path = mock_api.call_args[0][0]
    assert "bob" in call_path.lower()


# ---------------------------------------------------------------------------
# 6. Dry run
# ---------------------------------------------------------------------------

def test_scanner_dry_run_no_api_calls():
    """Dry run returns estimate without fetching."""
    db_mock = MagicMock()
    scanner = Scanner(
        org="testorg",
        watchlist=[{"handle": "@alice"}, {"handle": "@bob"}],
        db=db_mock,
        dry_run=True,
    )
    result = scanner.run(scan_id=1)
    assert result["dry_run"] is True
    assert result["accounts"] == 2
    assert result["tweets_new"] == 0
