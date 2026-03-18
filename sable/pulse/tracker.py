"""SocialData.tools API integration for tweet fetching and snapshots."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import httpx

from sable import config as cfg
from sable.pulse import db
from sable.shared.paths import sable_home

_CACHE_DIR = sable_home() / "pulse_cache"
_BASE_URL = "https://api.socialdata.tools"


def _cache_path(key: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{key}.json"


def _load_cache(key: str, max_age_seconds: int = 300) -> Optional[dict]:
    path = _cache_path(key)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > max_age_seconds:
        return None
    with open(path) as f:
        return json.load(f)


def _save_cache(key: str, data: dict) -> None:
    with open(_cache_path(key), "w") as f:
        json.dump(data, f)


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {cfg.require_key('socialdata_api_key')}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Mock data for testing without API key
# ---------------------------------------------------------------------------

def _mock_tweets(handle: str, count: int) -> list[dict]:
    handle = handle.lstrip("@")
    return [
        {
            "id_str": f"mock_{handle}_{i}",
            "full_text": f"Mock tweet {i} from @{handle} — this is test data",
            "created_at": "2026-03-17T12:00:00Z",
            "user": {"screen_name": handle, "followers_count": 10000},
            "favorite_count": 100 * (i + 1),
            "retweet_count": 20 * (i + 1),
            "reply_count": 10 * (i + 1),
            "views_count": 5000 * (i + 1),
            "bookmark_count": 5 * (i + 1),
            "quote_count": 3 * (i + 1),
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

async def _fetch_user_tweets_async(handle: str, count: int = 20) -> list[dict]:
    handle = handle.lstrip("@")
    cache_key = f"tweets_{handle}_{count}"
    cached = _load_cache(cache_key, max_age_seconds=600)
    if cached:
        return cached.get("tweets", [])

    async with httpx.AsyncClient(headers=_get_headers(), timeout=30) as client:
        resp = await client.get(
            f"{_BASE_URL}/twitter/user/{handle}/tweets",
            params={"type": "tweets", "limit": count},
        )
        resp.raise_for_status()
        data = resp.json()

    tweets = data.get("tweets", data.get("data", []))
    _save_cache(cache_key, {"tweets": tweets})
    return tweets


async def _fetch_tweet_metrics_async(tweet_id: str) -> dict:
    cache_key = f"tweet_{tweet_id}"
    cached = _load_cache(cache_key, max_age_seconds=60)
    if cached:
        return cached

    async with httpx.AsyncClient(headers=_get_headers(), timeout=30) as client:
        resp = await client.get(f"{_BASE_URL}/twitter/tweets/{tweet_id}")
        resp.raise_for_status()
        data = resp.json()

    _save_cache(cache_key, data)
    return data


def fetch_user_tweets(handle: str, count: int = 20, mock: bool = False) -> list[dict]:
    if mock:
        return _mock_tweets(handle, count)
    return asyncio.run(_fetch_user_tweets_async(handle, count))


def snapshot_account(handle: str, mock: bool = False) -> list[dict]:
    """
    Fetch recent tweets and record snapshots in the database.
    Returns list of ingested tweet dicts.
    """
    db.migrate()
    handle = handle if handle.startswith("@") else f"@{handle}"
    tweets = fetch_user_tweets(handle, count=50, mock=mock)

    for tweet in tweets:
        post_id = tweet.get("id_str", tweet.get("id", ""))
        if not post_id:
            continue

        db.insert_post(
            post_id=str(post_id),
            account_handle=handle,
            text=tweet.get("full_text", tweet.get("text", "")),
            url=f"https://twitter.com/i/web/status/{post_id}",
            posted_at=tweet.get("created_at", ""),
        )

        db.insert_snapshot(
            post_id=str(post_id),
            likes=tweet.get("favorite_count", 0),
            retweets=tweet.get("retweet_count", 0),
            replies=tweet.get("reply_count", 0),
            views=tweet.get("views_count", tweet.get("impression_count", 0)),
            bookmarks=tweet.get("bookmark_count", 0),
            quotes=tweet.get("quote_count", 0),
        )

    # Also record follower stats
    if tweets:
        user = tweets[0].get("user", {})
        db.insert_account_stats(
            handle=handle,
            followers=user.get("followers_count", 0),
            following=user.get("friends_count", 0),
            tweet_count=user.get("statuses_count", 0),
        )

    return tweets
