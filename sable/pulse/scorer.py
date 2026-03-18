"""Engagement scoring and percentile ranking."""
from __future__ import annotations

from typing import Optional


def engagement_rate(
    likes: int,
    retweets: int,
    replies: int,
    quotes: int,
    followers: int,
) -> float:
    """Standard engagement rate: (likes + RT + replies + quotes) / followers * 100"""
    if followers <= 0:
        return 0.0
    total = likes + retweets + replies + quotes
    return round((total / followers) * 100, 4)


def virality_score(
    retweets: int,
    quotes: int,
    views: int,
) -> float:
    """Virality = (RT + quotes) / views * 1000 (per-mille)"""
    if views <= 0:
        return 0.0
    return round(((retweets + quotes) / views) * 1000, 4)


def conversation_score(
    replies: int,
    quotes: int,
    views: int,
) -> float:
    """Conversation rate = (replies + quotes) / views * 1000"""
    if views <= 0:
        return 0.0
    return round(((replies + quotes) / views) * 1000, 4)


def score_post(snapshot: dict, followers: int = 1000) -> dict:
    """Compute all scores for a post snapshot."""
    likes = snapshot.get("likes", 0)
    rts = snapshot.get("retweets", 0)
    replies = snapshot.get("replies", 0)
    views = snapshot.get("views", 0)
    quotes = snapshot.get("quotes", 0)

    return {
        "engagement_rate": engagement_rate(likes, rts, replies, quotes, followers),
        "virality_score": virality_score(rts, quotes, views),
        "conversation_score": conversation_score(replies, quotes, views),
        "likes": likes,
        "retweets": rts,
        "replies": replies,
        "views": views,
        "quotes": quotes,
    }


def percentile_rank(value: float, all_values: list[float]) -> float:
    """Return percentile rank (0-100) of value in distribution."""
    if not all_values:
        return 0.0
    below = sum(1 for v in all_values if v < value)
    return round((below / len(all_values)) * 100, 1)


def rank_posts(scored_posts: list[dict], metric: str = "engagement_rate") -> list[dict]:
    """Sort posts by metric descending and add rank/percentile fields."""
    all_values = [p.get(metric, 0) for p in scored_posts]
    ranked = sorted(scored_posts, key=lambda p: p.get(metric, 0), reverse=True)
    for i, post in enumerate(ranked):
        post["rank"] = i + 1
        post["percentile"] = percentile_rank(post.get(metric, 0), all_values)
    return ranked
