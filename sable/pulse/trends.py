"""SocialData niche search and optional Grok integration."""
from __future__ import annotations

import asyncio

from sable.shared.socialdata import socialdata_get_async


async def _search_tweets_async(query: str, count: int = 20) -> list[dict]:
    data = await socialdata_get_async(
        "/twitter/search",
        params={"query": query, "type": "Latest", "count": count},
    )
    return data.get("tweets", data.get("data", []))


def search_niche(query: str, count: int = 20, mock: bool = False) -> list[dict]:
    """Search for trending tweets in a niche."""
    if mock:
        return [
            {
                "id_str": f"trend_{i}",
                "full_text": f"Mock trending tweet {i} about {query}",
                "favorite_count": 500 * (i + 1),
                "retweet_count": 100 * (i + 1),
                "user": {"screen_name": f"influencer_{i}", "followers_count": 50000},
            }
            for i in range(min(count, 5))
        ]
    return asyncio.run(_search_tweets_async(query, count))


def get_trending_topics(niche_keywords: list[str], mock: bool = False) -> list[dict]:
    """
    Search for trending content across niche keywords.
    Returns aggregated list sorted by engagement.
    """
    results = []
    for kw in niche_keywords[:3]:  # limit API calls
        tweets = search_niche(kw, count=10, mock=mock)
        for t in tweets:
            t["_query"] = kw
            results.append(t)

    # Sort by likes + retweets
    results.sort(
        key=lambda t: t.get("favorite_count", 0) + t.get("retweet_count", 0) * 3,
        reverse=True,
    )
    return results
