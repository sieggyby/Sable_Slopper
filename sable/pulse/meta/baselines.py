"""Dual baseline storage and comparison."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sable.pulse.meta.normalize import AuthorNormalizedTweet
from sable.pulse.meta.quality import aggregate_lifts

_MIN_BASELINE_SAMPLES = 4  # minimum tweets to store a format baseline


def compute_and_store_baseline(
    org: str,
    format_bucket: str,
    tweets: list[AuthorNormalizedTweet],
    period_days: int,
    db,
    method: str = "weighted_mean",
) -> Optional[float]:
    """Compute aggregate lift for a format bucket over period_days and store in DB.

    Returns the computed avg_total_lift, or None if insufficient data.
    """
    if not tweets:
        return None

    avg_lift = aggregate_lifts(tweets, method=method)
    unique_authors = len({t.author_handle for t in tweets})

    db.insert_format_baseline(
        org=org,
        format_bucket=format_bucket,
        period_days=period_days,
        avg_total_lift=avg_lift,
        sample_count=len(tweets),
        unique_authors=unique_authors,
    )
    return avg_lift


def get_baseline_lift(org: str, format_bucket: str, period_days: int, db) -> Optional[float]:
    """Get most recent stored baseline lift for a format."""
    rows = db.get_format_baselines(org, format_bucket, period_days, limit=1)
    if rows:
        return rows[0]["avg_total_lift"]
    return None


def get_dual_baselines(
    org: str,
    format_bucket: str,
    db,
    long_days: int = 30,
    short_days: int = 7,
) -> tuple[Optional[float], Optional[float]]:
    """Return (lift_30d, lift_7d) baselines for a format bucket.

    Returns (None, None) if baselines don't exist yet.
    """
    lift_30d = get_baseline_lift(org, format_bucket, long_days, db)
    lift_7d = get_baseline_lift(org, format_bucket, short_days, db)
    return lift_30d, lift_7d


def compute_baselines_from_db(
    org: str,
    db,
    long_days: int = 30,
    short_days: int = 7,
    method: str = "weighted_mean",
) -> dict[str, tuple[Optional[float], Optional[float]]]:
    """Compute and store baselines for all format buckets from stored DB tweet data.

    Iterates all FORMAT_BUCKETS, fetches historical tweets from DB for each,
    aggregates lifts over long_days and short_days windows, stores the results
    via db.insert_format_baseline(), and returns a dict of
    {format_bucket: (lift_30d, lift_7d)}. Either value is None if insufficient
    data exists for that window.
    """
    from sable.pulse.meta.fingerprint import FORMAT_BUCKETS
    from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality

    result: dict[str, tuple[Optional[float], Optional[float]]] = {}

    for bucket in FORMAT_BUCKETS:
        # Get tweets for long period
        rows_long = db.get_tweets_since(org, long_days, format_bucket=bucket)
        rows_short = db.get_tweets_since(org, short_days, format_bucket=bucket)

        tweets_long = _rows_to_normalized(rows_long)
        tweets_short = _rows_to_normalized(rows_short)

        lift_30d = None
        lift_7d = None

        if len(tweets_long) >= _MIN_BASELINE_SAMPLES:
            lift_30d = aggregate_lifts(tweets_long, method=method)
            unique_authors = len({t.author_handle for t in tweets_long})
            db.insert_format_baseline(org, bucket, long_days, lift_30d, len(tweets_long), unique_authors)

        if len(tweets_short) >= _MIN_BASELINE_SAMPLES:
            lift_7d = aggregate_lifts(tweets_short, method=method)
            unique_authors = len({t.author_handle for t in tweets_short})
            db.insert_format_baseline(org, bucket, short_days, lift_7d, len(tweets_short), unique_authors)

        result[bucket] = (lift_30d, lift_7d)

    return result


def _rows_to_normalized(rows: list[dict]) -> list[AuthorNormalizedTweet]:
    """Convert DB rows to AuthorNormalizedTweet objects for aggregation."""
    from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality

    tweets = []
    for row in rows:
        if row.get("total_lift") is None:
            continue
        grade = row.get("author_quality_grade", "fallback")
        weight = row.get("author_quality_weight", 0.25) or 0.25
        aq = AuthorQuality(
            grade=grade,
            total_tweets=0,
            total_scans=0,
            reasons=[],
            weight=weight,
        )
        tweets.append(AuthorNormalizedTweet(
            tweet_id=row.get("tweet_id", ""),
            author_handle=row.get("author_handle", ""),
            format_bucket=row.get("format_bucket", ""),
            attributes=row.get("attributes", []),
            posted_at=row.get("posted_at", ""),
            text=row.get("text", ""),
            likes=row.get("likes", 0),
            replies=row.get("replies", 0),
            reposts=row.get("reposts", 0),
            quotes=row.get("quotes", 0),
            bookmarks=row.get("bookmarks", 0),
            video_views=row.get("video_views", 0),
            author_followers=row.get("author_followers", 0),
            author_median_likes=row.get("author_median_likes") or 0.0,
            author_median_replies=row.get("author_median_replies") or 0.0,
            author_median_reposts=row.get("author_median_reposts") or 0.0,
            author_median_quotes=row.get("author_median_quotes") or 0.0,
            author_median_total=row.get("author_median_total") or 0.0,
            likes_lift=row.get("likes_lift") or 0.0,
            replies_lift=row.get("replies_lift") or 0.0,
            reposts_lift=row.get("reposts_lift") or 0.0,
            quotes_lift=row.get("quotes_lift") or 0.0,
            total_lift=row.get("total_lift") or 0.0,
            author_median_same_format=row.get("author_median_same_format") or 0.0,
            format_lift=row.get("format_lift") or 0.0,
            format_lift_reliable=bool(row.get("format_lift_reliable", False)),
            author_quality=aq,
        ))
    return tweets
