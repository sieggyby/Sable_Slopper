"""Author-relative normalization: the core analytical engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Optional

MAX_LIFT = 20.0  # why: 20× is the empirical ceiling beyond which signal is noise/outlier


@dataclass
class AuthorQuality:
    grade: str          # "strong" | "adequate" | "weak" | "fallback"
    total_tweets: int
    total_scans: int
    reasons: list[str]
    weight: float       # 0.0-1.0, used to downweight noisy authors in aggregation


def assess_author_quality(author_history: list[dict], format_bucket: str) -> AuthorQuality:
    """Grade an author's data quality for normalization reliability."""
    total = len(author_history)
    same_format = len([t for t in author_history if t.get("format_bucket") == format_bucket])

    if total < 5:
        # Insufficient data → fallback
        return AuthorQuality(
            grade="fallback",
            total_tweets=total,
            total_scans=0,
            reasons=[f"very thin history ({total} tweets)"],
            weight=0.25,
        )

    reasons = []
    score = 0

    # Total history depth
    if total >= 20:
        score += 3
    elif total >= 10:
        score += 2
    else:  # 5-9
        score += 1
        reasons.append(f"thin history ({total} tweets)")

    # Same-format depth
    if same_format >= 5:
        score += 2
    elif same_format >= 3:
        score += 1
        reasons.append(f"limited same-format history ({same_format} tweets)")
    else:
        reasons.append(f"insufficient same-format history ({same_format} tweets)")

    # Engagement distribution stability
    totals = [
        t.get("likes", 0) + t.get("replies", 0) + t.get("reposts", 0) + t.get("quotes", 0)
        for t in author_history
    ]
    if totals:
        mean_total = sum(totals) / len(totals)
        med_total = median(totals)
        if mean_total > med_total * 3 and total < 15:
            reasons.append("skewed engagement distribution — median may not be stable")
        else:
            score += 1

    if score >= 5:
        grade, weight = "strong", 1.0  # noqa: F841  # why: score 5-6 → full reliability
        return AuthorQuality("strong", total, 0, reasons or ["sufficient depth"], 1.0)
    elif score >= 3:
        return AuthorQuality("adequate", total, 0, reasons or ["acceptable depth"], 0.8)  # why: 0.8 = mild downweight for thinner history
    elif score >= 1:
        return AuthorQuality("weak", total, 0, reasons, 0.5)  # why: 0.5 = half-weight, unreliable but usable
    else:
        return AuthorQuality("fallback", total, 0, reasons, 0.25)  # why: 0.25 = near-discard weight


@dataclass
class AuthorNormalizedTweet:
    tweet_id: str
    author_handle: str
    format_bucket: str
    attributes: list[str]
    posted_at: str
    text: str

    # Raw engagement
    likes: int
    replies: int
    reposts: int
    quotes: int
    bookmarks: int
    video_views: int

    # Author context
    author_followers: int
    author_median_likes: float
    author_median_replies: float
    author_median_reposts: float
    author_median_quotes: float
    author_median_total: float

    # Author-relative lifts (primary analytical signal)
    likes_lift: Optional[float]
    replies_lift: Optional[float]
    reposts_lift: Optional[float]
    quotes_lift: Optional[float]
    total_lift: Optional[float]

    # Same-format lift
    author_median_same_format: float
    format_lift: Optional[float]
    format_lift_reliable: bool

    # Quality metadata
    author_quality: AuthorQuality


def compute_author_lift(tweet: dict, author_history: list[dict]) -> AuthorNormalizedTweet:
    """Compute author-relative lifts for a tweet.

    If author_history is empty or too thin, falls back to per-follower metrics.
    """
    format_bucket = tweet.get("format_bucket", "standalone_text")

    if len(author_history) < 5:
        return _compute_fallback(tweet, format_bucket, author_history)

    author_quality = assess_author_quality(author_history, format_bucket)

    median_likes = median([t.get("likes", 0) for t in author_history])
    median_replies = median([t.get("replies", 0) for t in author_history])
    median_reposts = median([t.get("reposts", 0) for t in author_history])
    median_quotes = median([t.get("quotes", 0) for t in author_history])
    median_total = median([
        t.get("likes", 0) + t.get("replies", 0) + t.get("reposts", 0) + t.get("quotes", 0)
        for t in author_history
    ])

    # Minimum stable denominator
    # Floor = max(2, 5% of median_total). Prevents extreme lifts from near-zero baselines.
    min_denom = max(2, int(median_total * 0.05)) if median_total else 2
    median_likes = max(median_likes, min_denom)
    median_replies = max(median_replies, min_denom)
    median_reposts = max(median_reposts, min_denom)
    median_quotes = max(median_quotes, min_denom)
    median_total = max(median_total, min_denom * 4)

    # Same-format median
    same_format = [t for t in author_history if t.get("format_bucket") == format_bucket]
    if len(same_format) >= 5:
        median_same_format = max(
            median([
                t.get("likes", 0) + t.get("replies", 0) + t.get("reposts", 0) + t.get("quotes", 0)
                for t in same_format
            ]),
            min_denom * 4,
        )
        format_lift_reliable = True
    else:
        median_same_format = median_total
        format_lift_reliable = False

    total = (
        tweet.get("likes", 0) + tweet.get("replies", 0) +
        tweet.get("reposts", 0) + tweet.get("quotes", 0)
    )

    # Compute raw lifts
    raw_likes_lift = tweet.get("likes", 0) / median_likes
    raw_replies_lift = tweet.get("replies", 0) / median_replies
    raw_reposts_lift = tweet.get("reposts", 0) / median_reposts
    raw_quotes_lift = tweet.get("quotes", 0) / median_quotes
    raw_total_lift = total / median_total
    raw_format_lift = total / median_same_format

    # Clamp at MAX_LIFT (20x)
    likes_lift = min(raw_likes_lift, MAX_LIFT)
    replies_lift = min(raw_replies_lift, MAX_LIFT)
    reposts_lift = min(raw_reposts_lift, MAX_LIFT)
    quotes_lift = min(raw_quotes_lift, MAX_LIFT)
    total_lift = min(raw_total_lift, MAX_LIFT)
    format_lift = min(raw_format_lift, MAX_LIFT)

    return AuthorNormalizedTweet(
        tweet_id=tweet.get("tweet_id", ""),
        author_handle=tweet.get("author_handle", ""),
        format_bucket=format_bucket,
        attributes=tweet.get("attributes", []),
        posted_at=tweet.get("posted_at", ""),
        text=tweet.get("text", ""),
        likes=tweet.get("likes", 0),
        replies=tweet.get("replies", 0),
        reposts=tweet.get("reposts", 0),
        quotes=tweet.get("quotes", 0),
        bookmarks=tweet.get("bookmarks", 0),
        video_views=tweet.get("video_views", 0),
        author_followers=tweet.get("author_followers", 0),
        author_median_likes=median_likes,
        author_median_replies=median_replies,
        author_median_reposts=median_reposts,
        author_median_quotes=median_quotes,
        author_median_total=median_total,
        likes_lift=likes_lift,
        replies_lift=replies_lift,
        reposts_lift=reposts_lift,
        quotes_lift=quotes_lift,
        total_lift=total_lift,
        author_median_same_format=median_same_format,
        format_lift=format_lift if format_lift_reliable else None,  # AR5-17: None when unreliable
        format_lift_reliable=format_lift_reliable,
        author_quality=author_quality,
    )


def _compute_fallback(tweet: dict, format_bucket: str,
                       author_history: list[dict]) -> AuthorNormalizedTweet:
    """Per-follower fallback when author history is too thin."""
    author_quality = AuthorQuality(
        grade="fallback",
        total_tweets=len(author_history),
        total_scans=0,
        reasons=["insufficient history for author-relative normalization — using per-follower fallback"],
        weight=0.25,
    )

    # AR5-18: zero history → all lifts are undefined (None), not misleadingly 0
    if len(author_history) == 0:
        return AuthorNormalizedTweet(
            tweet_id=tweet.get("tweet_id", ""),
            author_handle=tweet.get("author_handle", ""),
            format_bucket=format_bucket,
            attributes=tweet.get("attributes", []),
            posted_at=tweet.get("posted_at", ""),
            text=tweet.get("text", ""),
            likes=tweet.get("likes", 0),
            replies=tweet.get("replies", 0),
            reposts=tweet.get("reposts", 0),
            quotes=tweet.get("quotes", 0),
            bookmarks=tweet.get("bookmarks", 0),
            video_views=tweet.get("video_views", 0),
            author_followers=tweet.get("author_followers", 0),
            author_median_likes=0.0,
            author_median_replies=0.0,
            author_median_reposts=0.0,
            author_median_quotes=0.0,
            author_median_total=0.0,
            likes_lift=None,
            replies_lift=None,
            reposts_lift=None,
            quotes_lift=None,
            total_lift=None,
            author_median_same_format=0.0,
            format_lift=None,
            format_lift_reliable=False,
            author_quality=author_quality,
        )

    followers = tweet.get("author_followers", 1) or 1
    total = (
        tweet.get("likes", 0) + tweet.get("replies", 0) +
        tweet.get("reposts", 0) + tweet.get("quotes", 0)
    )
    # Per-follower engagement rate vs typical (0.5% per 1000 followers as baseline)
    baseline_per_1k = 5.0  # why: industry rough baseline — 5 engagements per 1k followers
    per_k_actual = (total / followers) * 1000
    total_lift = min(per_k_actual / baseline_per_1k if baseline_per_1k else 1.0, MAX_LIFT)
    total_lift = max(total_lift, 0.0)

    # Fallback lift for all individual metrics — use total_lift as proxy
    return AuthorNormalizedTweet(
        tweet_id=tweet.get("tweet_id", ""),
        author_handle=tweet.get("author_handle", ""),
        format_bucket=format_bucket,
        attributes=tweet.get("attributes", []),
        posted_at=tweet.get("posted_at", ""),
        text=tweet.get("text", ""),
        likes=tweet.get("likes", 0),
        replies=tweet.get("replies", 0),
        reposts=tweet.get("reposts", 0),
        quotes=tweet.get("quotes", 0),
        bookmarks=tweet.get("bookmarks", 0),
        video_views=tweet.get("video_views", 0),
        author_followers=followers,
        author_median_likes=0.0,
        author_median_replies=0.0,
        author_median_reposts=0.0,
        author_median_quotes=0.0,
        author_median_total=0.0,
        likes_lift=total_lift,
        replies_lift=total_lift,
        reposts_lift=total_lift,
        quotes_lift=total_lift,
        total_lift=total_lift,
        author_median_same_format=0.0,
        format_lift=total_lift,
        format_lift_reliable=False,
        author_quality=author_quality,
    )


def weighted_mean_lift(tweets: list[AuthorNormalizedTweet]) -> float:
    """Weighted average of total_lift, where weight = author quality weight."""
    weighted_sum = 0.0
    total_weight = 0.0
    for tweet in tweets:
        if tweet.total_lift is None:
            continue
        total_weight += tweet.author_quality.weight
        weighted_sum += tweet.total_lift * tweet.author_quality.weight
    if total_weight == 0:
        return 0.0
    return weighted_sum / total_weight
