"""Pulse API routes — content performance data."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query

from sable.serve.deps import get_pulse_db, get_meta_db
from sable.roster.manager import list_accounts

logger = logging.getLogger(__name__)
router = APIRouter()


def _engagement(snap: sqlite3.Row) -> int:
    return (
        (snap["likes"] or 0)
        + (snap["retweets"] or 0)
        + (snap["replies"] or 0)
        + (snap["quotes"] or 0)
        + (snap["bookmarks"] or 0)
    )


@router.get("/performance/{org}")
def pulse_performance(org: str, days: int = Query(30, ge=1, le=365)):
    """Content performance data for an org over the last N days."""
    pulse = get_pulse_db()
    accounts = list_accounts(org=org)
    if not accounts:
        return {"error": "No accounts found for org", "org": org}

    handles = [a.handle for a in accounts]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    # Fetch posts for org's accounts within window
    placeholders = ",".join("?" for _ in handles)
    posts = pulse.execute(
        f"""SELECT p.*, s.likes, s.retweets, s.replies, s.views,
                   s.bookmarks, s.quotes, s.taken_at AS snap_at
            FROM posts p
            LEFT JOIN (
                SELECT post_id, likes, retweets, replies, views, bookmarks, quotes, taken_at,
                       ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY taken_at DESC) AS rn
                FROM snapshots
            ) s ON s.post_id = p.id AND s.rn = 1
            WHERE p.account_handle IN ({placeholders})
              AND p.posted_at >= ?
            ORDER BY p.posted_at DESC""",
        (*handles, cutoff),
    ).fetchall()

    sable_posts = []
    organic_posts = []
    for p in posts:
        row = dict(p)
        eng = _engagement(p)
        row["engagement"] = eng
        if row.get("sable_content_type") or row.get("sable_content_path"):
            sable_posts.append(row)
        else:
            organic_posts.append(row)

    sable_ids = {p["id"] for p in sable_posts}

    sable_eng = sum(p["engagement"] for p in sable_posts)
    organic_eng = sum(p["engagement"] for p in organic_posts)
    total_eng = sable_eng + organic_eng

    sable_avg = sable_eng / len(sable_posts) if sable_posts else 0
    organic_avg = organic_eng / len(organic_posts) if organic_posts else 0

    # By-format breakdown (sable posts only)
    by_format: dict[str, dict] = {}
    for p in sable_posts:
        fmt = p.get("sable_content_type") or "unknown"
        bucket = by_format.setdefault(fmt, {"format": fmt, "count": 0, "total_engagement": 0})
        bucket["count"] += 1
        bucket["total_engagement"] += p["engagement"]
    for bucket in by_format.values():
        bucket["avg_engagement"] = (
            bucket["total_engagement"] / bucket["count"] if bucket["count"] else 0
        )

    # Weekly trend
    weekly: dict[str, dict] = {}
    for p in sable_posts + organic_posts:
        posted_at = p.get("posted_at") or ""
        if len(posted_at) >= 10:
            try:
                dt = datetime.fromisoformat(posted_at[:19])
                week = dt.strftime("%YW%W")
            except ValueError:
                continue
        else:
            continue
        is_sable = p["id"] in sable_ids
        w = weekly.setdefault(week, {"week": week, "sable_engagement": 0, "organic_engagement": 0})
        if is_sable:
            w["sable_engagement"] += p["engagement"]
        else:
            w["organic_engagement"] += p["engagement"]

    for w in weekly.values():
        total = w["sable_engagement"] + w["organic_engagement"]
        w["sable_share"] = round(w["sable_engagement"] / total, 3) if total else 0

    # Check meta-informed posts
    meta_informed_count = 0
    meta_informed_eng = 0
    non_meta_eng = 0
    try:
        meta = get_meta_db()
        baselines = meta.execute(
            "SELECT DISTINCT format_bucket FROM format_baselines WHERE org = ?",
            (org,),
        ).fetchall()
        meta_formats = {r["format_bucket"] for r in baselines}
        for p in sable_posts:
            if p.get("sable_content_type") in meta_formats:
                meta_informed_count += 1
                meta_informed_eng += p["engagement"]
            else:
                non_meta_eng += p["engagement"]
    except Exception as e:
        logger.warning("Meta DB unavailable for performance metrics: %s", e)
        meta_formats = set()

    non_meta_count = len(sable_posts) - meta_informed_count

    return {
        "total_posts": len(posts),
        "sable_posts": len(sable_posts),
        "organic_posts": len(organic_posts),
        "sable_share_of_engagement": round(sable_eng / total_eng, 3) if total_eng else 0,
        "sable_avg_engagement": round(sable_avg, 1),
        "organic_avg_engagement": round(organic_avg, 1),
        "sable_lift_vs_organic": round(sable_avg / organic_avg, 2) if organic_avg else 0,
        "top_performing_formats": sorted(
            by_format.values(), key=lambda b: b["avg_engagement"], reverse=True
        ),
        "by_format": list(by_format.values()),
        "weekly_trend": sorted(weekly.values(), key=lambda w: w["week"]),
        "meta_informed": {
            "meta_informed_posts": meta_informed_count,
            "meta_informed_avg": round(
                meta_informed_eng / meta_informed_count, 1
            ) if meta_informed_count else 0,
            "non_meta_avg": round(
                non_meta_eng / non_meta_count, 1
            ) if non_meta_count else 0,
            "meta_lift": round(
                (meta_informed_eng / meta_informed_count)
                / (non_meta_eng / non_meta_count), 2
            ) if meta_informed_count and non_meta_count and non_meta_eng else 0,
        },
    }


@router.get("/posting-log/{org}")
def posting_log(org: str, days: int = Query(30, ge=1, le=365)):
    """Raw posting log for an org."""
    pulse = get_pulse_db()
    accounts = list_accounts(org=org)
    if not accounts:
        return []

    handles = [a.handle for a in accounts]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join("?" for _ in handles)

    rows = pulse.execute(
        f"""SELECT p.id, p.url, p.text, p.posted_at, p.sable_content_type,
                   s.likes, s.retweets, s.replies, s.views, s.bookmarks, s.quotes
            FROM posts p
            LEFT JOIN (
                SELECT post_id, likes, retweets, replies, views, bookmarks, quotes,
                       ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY taken_at DESC) AS rn
                FROM snapshots
            ) s ON s.post_id = p.id AND s.rn = 1
            WHERE p.account_handle IN ({placeholders})
              AND p.posted_at >= ?
            ORDER BY p.posted_at DESC""",
        (*handles, cutoff),
    ).fetchall()

    return [dict(r) for r in rows]
