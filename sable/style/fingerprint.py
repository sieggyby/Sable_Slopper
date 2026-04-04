"""Style fingerprinting — format distribution analysis for managed and watchlist accounts."""
from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Coarse bucket mapping: covers both scanned_tweets.format_bucket
# AND posts.sable_content_type vocabularies
_COARSE_MAP: dict[str, str] = {
    # scanned_tweets format_bucket values
    "standalone_text": "text",
    "thread": "text",
    "quote_tweet": "text",
    "short_clip": "clip",
    "long_video": "clip",
    # posts sable_content_type values
    "text": "text",
    "clip": "clip",
    "meme": "image",
    "faceswap": "image",
    "unknown": "other",
}

MIN_POSTS = 10  # minimum posts to produce a fingerprint


def _coarse_bucket(format_bucket: str) -> str:
    """Map fine-grained format_bucket to coarse category."""
    return _COARSE_MAP.get(format_bucket, format_bucket)


def fingerprint_managed(
    handle: str,
    pulse_conn: sqlite3.Connection,
    meta_conn: sqlite3.Connection | None = None,
) -> dict[str, float]:
    """Compute format distribution for a managed account.

    Queries pulse.db posts for sable_content_type distribution.
    If meta_conn provided and handle exists in scanned_tweets, adds
    thread length, media rate, link rate.

    Returns dict mapping coarse bucket → share (0.0-1.0), plus optional
    enrichment keys (media_rate, link_rate, avg_thread_length).
    Returns empty dict if fewer than MIN_POSTS.
    """
    rows = pulse_conn.execute(
        """SELECT sable_content_type, COUNT(*) as cnt
           FROM posts
           WHERE account_handle = ?
           GROUP BY sable_content_type""",
        (handle,),
    ).fetchall()

    total = sum(r["cnt"] for r in rows)
    if total < MIN_POSTS:
        return {}

    # Build coarse distribution
    coarse: dict[str, int] = {}
    for r in rows:
        bucket = _coarse_bucket(r["sable_content_type"] or "unknown")
        coarse[bucket] = coarse.get(bucket, 0) + r["cnt"]

    fp: dict[str, float] = {b: c / total for b, c in coarse.items()}

    # Enrich from meta.db if available
    if meta_conn is not None:
        norm_handle = handle if handle.startswith("@") else f"@{handle}"
        meta_rows = meta_conn.execute(
            """SELECT has_image, has_video, has_link, is_thread, thread_length
               FROM scanned_tweets
               WHERE author_handle = ?""",
            (norm_handle,),
        ).fetchall()
        if meta_rows:
            n = len(meta_rows)
            fp["media_rate"] = sum(
                1 for r in meta_rows if r["has_image"] or r["has_video"]
            ) / n
            fp["link_rate"] = sum(1 for r in meta_rows if r["has_link"]) / n
            threads = [r for r in meta_rows if r["is_thread"]]
            if threads:
                fp["avg_thread_length"] = sum(
                    r["thread_length"] for r in threads
                ) / len(threads)

    return fp


def fingerprint_watchlist(
    org: str,
    meta_conn: sqlite3.Connection,
    top_quintile: bool = True,
) -> dict[str, float]:
    """Compute format distribution for watchlist (top-performing authors).

    When top_quintile=True, filters to top 20% of authors by total_lift.
    Returns dict mapping coarse bucket → share, plus media_rate, link_rate.
    Returns empty dict if fewer than MIN_POSTS.
    """
    if top_quintile:
        rows = meta_conn.execute(
            """SELECT format_bucket, has_image, has_video, has_link,
                      is_thread, thread_length, author_handle
               FROM scanned_tweets
               WHERE org = ? AND total_lift IS NOT NULL
                 AND author_handle IN (
                     SELECT author_handle FROM (
                         SELECT author_handle, AVG(total_lift) as avg_lift
                         FROM scanned_tweets
                         WHERE org = ? AND total_lift IS NOT NULL
                         GROUP BY author_handle
                         HAVING COUNT(*) >= 3
                         ORDER BY avg_lift DESC
                         LIMIT (
                             SELECT MAX(1, COUNT(DISTINCT author_handle) / 5)
                             FROM scanned_tweets
                             WHERE org = ? AND total_lift IS NOT NULL
                         )
                     )
                 )""",
            (org, org, org),
        ).fetchall()
    else:
        rows = meta_conn.execute(
            """SELECT format_bucket, has_image, has_video, has_link,
                      is_thread, thread_length, author_handle
               FROM scanned_tweets
               WHERE org = ? AND total_lift IS NOT NULL""",
            (org,),
        ).fetchall()

    if len(rows) < MIN_POSTS:
        return {}

    # Coarse distribution
    coarse: dict[str, int] = {}
    total = len(rows)
    for r in rows:
        bucket = _coarse_bucket(r["format_bucket"] or "unknown")
        coarse[bucket] = coarse.get(bucket, 0) + 1

    fp: dict[str, float] = {b: c / total for b, c in coarse.items()}

    # Enrichment
    fp["media_rate"] = sum(
        1 for r in rows if r["has_image"] or r["has_video"]
    ) / total
    fp["link_rate"] = sum(1 for r in rows if r["has_link"]) / total

    threads = [r for r in rows if r["is_thread"]]
    if threads:
        fp["avg_thread_length"] = sum(
            r["thread_length"] for r in threads
        ) / len(threads)

    return fp
