"""Content attribution: what fraction of engagement came from Sable-produced content."""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SABLE_TYPES = {"clip", "meme", "faceswap", "text"}
_MIN_LIFT_SAMPLE = 3


def _engagement(likes: int, replies: int, retweets: int, quotes: int,
                bookmarks: int, views: int) -> float:
    return (
        (likes or 0) * 1.0
        + (replies or 0) * 3.0
        + (retweets or 0) * 4.0
        + (quotes or 0) * 5.0
        + (bookmarks or 0) * 2.0
        + (views or 0) * 0.5
    )


def _content_type_to_format_bucket(content_type: Optional[str],
                                    content_path: Optional[str]) -> Optional[str]:
    if content_type in ("meme", "faceswap"):
        return "single_image"
    if content_type == "text":
        return "standalone_text"
    if content_type == "clip":
        duration: Optional[float] = None
        if content_path:
            try:
                meta_path = Path(content_path).with_suffix(".meta.json")
                if meta_path.exists():
                    import json
                    data = json.loads(meta_path.read_text())
                    duration = data.get("duration")
            except Exception:
                pass
        if duration is not None and duration > 60:
            return "long_clip"
        return "short_clip"
    return None


@dataclass
class ContentAttribution:
    account_handle: str
    period_start: str
    period_end: str
    total_posts: int
    sable_posts: int
    organic_posts: int
    sable_share_of_posts: float
    total_engagement: float
    sable_engagement: float
    organic_engagement: float
    sable_share_of_engagement: float
    sable_avg_engagement: float
    organic_avg_engagement: float
    sable_lift_vs_organic: Optional[float]
    sable_by_format: dict
    organic_by_format: dict
    meta_informed_posts: int
    meta_informed_engagement: float
    meta_informed_avg: float
    non_meta_informed_avg: float
    meta_lift: Optional[float]
    meta_available: bool
    weekly_breakdown: list
    posts_excluded_no_snapshot: int


def compute_attribution(
    account_handle: str,
    days: int = 30,
    pulse_db_path: Optional[Path] = None,
    meta_db_path: Optional[Path] = None,
    org: Optional[str] = None,
) -> ContentAttribution:
    from sable.shared.paths import pulse_db_path as default_pulse, meta_db_path as default_meta

    pulse_path = pulse_db_path or default_pulse()
    meta_path = meta_db_path or default_meta()

    now = datetime.now(timezone.utc)
    period_start = (now - timedelta(days=days)).isoformat()
    period_end = now.isoformat()

    handle = account_handle if account_handle.startswith("@") else f"@{account_handle}"

    pulse_conn = sqlite3.connect(str(pulse_path))
    pulse_conn.row_factory = sqlite3.Row

    rows = pulse_conn.execute(
        """SELECT p.id, p.text, p.posted_at, p.sable_content_type, p.sable_content_path,
                  s.likes, s.retweets, s.replies, s.views, s.bookmarks, s.quotes
           FROM posts p
           LEFT JOIN snapshots s ON (
               p.id = s.post_id
               AND s.id = (SELECT MAX(s2.id) FROM snapshots s2 WHERE s2.post_id = p.id)
           )
           WHERE p.account_handle = ? AND p.posted_at >= ?
           ORDER BY p.posted_at DESC""",
        (handle, period_start),
    ).fetchall()
    pulse_conn.close()

    # Gather baselines from meta.db if org is provided
    meta_available = False
    baselines_by_bucket: dict[str, float] = {}
    if org:
        try:
            from sable.pulse.meta.db import get_format_baselines_as_of
            meta_conn = sqlite3.connect(str(meta_path))
            meta_conn.row_factory = sqlite3.Row
            baseline_rows = get_format_baselines_as_of(org, period_end, period_days=7, conn=meta_conn)
            meta_conn.close()
            if baseline_rows:
                meta_available = True
                for br in baseline_rows:
                    baselines_by_bucket[br["format_bucket"]] = br["avg_total_lift"]
        except Exception as e:
            logger.warning("pulse attribution: meta.db lookup failed (org=%s): %s", org, e)

    posts_excluded_no_snapshot = 0
    sable_posts = 0
    organic_posts = 0
    sable_engagement = 0.0
    organic_engagement = 0.0
    sable_by_format: dict[str, dict] = {}
    organic_by_format: dict[str, dict] = {}
    meta_informed_engagements: list[float] = []
    non_meta_informed_engagements: list[float] = []
    weekly: dict[str, dict] = {}

    for row in rows:
        ct = row["sable_content_type"]
        cp = row["sable_content_path"]
        is_sable = ct in _SABLE_TYPES

        # No snapshot → excluded from engagement
        if row["likes"] is None and row["views"] is None:
            posts_excluded_no_snapshot += 1
            continue

        eng = _engagement(
            row["likes"], row["replies"], row["retweets"],
            row["quotes"], row["bookmarks"], row["views"],
        )

        # Weekly breakdown
        try:
            dt = datetime.fromisoformat(row["posted_at"])
            iso = dt.isocalendar()
            week_key = f"{iso[0]}-W{iso[1]:02d}"
        except Exception:
            week_key = "unknown"
        if week_key not in weekly:
            weekly[week_key] = {"week": week_key, "sable": 0.0, "organic": 0.0}

        if is_sable:
            sable_posts += 1
            sable_engagement += eng
            weekly[week_key]["sable"] += eng

            bucket = _content_type_to_format_bucket(ct, cp)
            if bucket:
                if bucket not in sable_by_format:
                    sable_by_format[bucket] = {"posts": 0, "engagement": 0.0}
                sable_by_format[bucket]["posts"] += 1
                sable_by_format[bucket]["engagement"] += eng

            # Meta-informed classification
            if meta_available and bucket and bucket in baselines_by_bucket:
                meta_informed_engagements.append(eng)
            else:
                non_meta_informed_engagements.append(eng)
        else:
            organic_posts += 1
            organic_engagement += eng
            weekly[week_key]["organic"] += eng

            bucket = _content_type_to_format_bucket(ct, cp)
            fmt_key = bucket or (ct or "unknown")
            if fmt_key not in organic_by_format:
                organic_by_format[fmt_key] = {"posts": 0, "engagement": 0.0}
            organic_by_format[fmt_key]["posts"] += 1
            organic_by_format[fmt_key]["engagement"] += eng

    # Compute averages for by_format dicts
    for d in sable_by_format.values():
        d["avg"] = d["engagement"] / d["posts"] if d["posts"] else 0.0
    for d in organic_by_format.values():
        d["avg"] = d["engagement"] / d["posts"] if d["posts"] else 0.0

    total_posts = sable_posts + organic_posts
    total_engagement = sable_engagement + organic_engagement

    sable_share_of_posts = sable_posts / total_posts if total_posts else 0.0
    sable_share_of_engagement = sable_engagement / total_engagement if total_engagement else 0.0
    sable_avg_engagement = sable_engagement / sable_posts if sable_posts else 0.0
    organic_avg_engagement = organic_engagement / organic_posts if organic_posts else 0.0

    if organic_posts == 0 or sable_posts < 2 or organic_posts < 2:
        sable_lift_vs_organic = None
    else:
        sable_lift_vs_organic = (sable_avg_engagement - organic_avg_engagement) / organic_avg_engagement if organic_avg_engagement else None

    meta_informed_posts = len(meta_informed_engagements)
    meta_informed_engagement = sum(meta_informed_engagements)
    meta_informed_avg = meta_informed_engagement / meta_informed_posts if meta_informed_posts else 0.0
    non_meta_informed_avg = (
        sum(non_meta_informed_engagements) / len(non_meta_informed_engagements)
        if non_meta_informed_engagements else 0.0
    )

    if meta_informed_posts < 2 or len(non_meta_informed_engagements) < 2:
        meta_lift = None
    else:
        meta_lift = (
            (meta_informed_avg - non_meta_informed_avg) / non_meta_informed_avg
            if non_meta_informed_avg else None
        )

    # Weekly breakdown: add share
    weekly_breakdown = []
    for w in sorted(weekly.values(), key=lambda x: x["week"]):
        total_w = w["sable"] + w["organic"]
        share = w["sable"] / total_w if total_w else 0.0
        weekly_breakdown.append({**w, "share": share})

    return ContentAttribution(
        account_handle=handle,
        period_start=period_start,
        period_end=period_end,
        total_posts=total_posts,
        sable_posts=sable_posts,
        organic_posts=organic_posts,
        sable_share_of_posts=sable_share_of_posts,
        total_engagement=total_engagement,
        sable_engagement=sable_engagement,
        organic_engagement=organic_engagement,
        sable_share_of_engagement=sable_share_of_engagement,
        sable_avg_engagement=sable_avg_engagement,
        organic_avg_engagement=organic_avg_engagement,
        sable_lift_vs_organic=sable_lift_vs_organic,
        sable_by_format=sable_by_format,
        organic_by_format=organic_by_format,
        meta_informed_posts=meta_informed_posts,
        meta_informed_engagement=meta_informed_engagement,
        meta_informed_avg=meta_informed_avg,
        non_meta_informed_avg=non_meta_informed_avg,
        meta_lift=meta_lift,
        meta_available=meta_available,
        weekly_breakdown=weekly_breakdown,
        posts_excluded_no_snapshot=posts_excluded_no_snapshot,
    )


def render_attribution_report(attr: ContentAttribution) -> str:
    lines = []
    lines.append(f"# Content Attribution — {attr.account_handle}")
    lines.append(f"Period: {attr.period_start[:10]} to {attr.period_end[:10]}")
    lines.append("")

    lines.append("## Summary")
    lines.append(f"- Total posts: {attr.total_posts} (Sable: {attr.sable_posts}, Organic: {attr.organic_posts})")
    lines.append(f"- Sable share of posts: {attr.sable_share_of_posts:.0%}")
    lines.append(f"- Sable share of engagement: {attr.sable_share_of_engagement:.0%}")
    lines.append(f"- Sable avg engagement: {attr.sable_avg_engagement:.1f}")
    lines.append(f"- Organic avg engagement: {attr.organic_avg_engagement:.1f}")
    lines.append(
        "  _(Sable posts are curated content; organic posts are all other activity — "
        "not a controlled comparison.)_"
    )
    if attr.posts_excluded_no_snapshot:
        lines.append(f"- Posts excluded (no snapshot): {attr.posts_excluded_no_snapshot}")
    lines.append("")

    lines.append("## Format Breakdown")
    lines.append("| format | sable posts | sable avg | organic posts | organic avg | lift |")
    lines.append("|--------|-------------|-----------|---------------|-------------|------|")
    all_buckets = sorted(set(list(attr.sable_by_format.keys()) + list(attr.organic_by_format.keys())))
    for bucket in all_buckets:
        sb = attr.sable_by_format.get(bucket, {"posts": 0, "avg": 0.0})
        ob = attr.organic_by_format.get(bucket, {"posts": 0, "avg": 0.0})
        if ob["avg"] and sb["avg"] and sb.get("posts", 0) >= _MIN_LIFT_SAMPLE and ob.get("posts", 0) >= _MIN_LIFT_SAMPLE:
            lift_str = f"{(sb['avg'] - ob['avg']) / ob['avg']:+.0%}"
        elif ob["avg"] and sb["avg"]:
            lift_str = "n/a (thin)"
        else:
            lift_str = "n/a"
        lines.append(
            f"| {bucket} | {sb['posts']} | {sb['avg']:.1f} | {ob['posts']} | {ob['avg']:.1f} | {lift_str} |"
        )
    lines.append("")

    lines.append("## Pulse Meta Impact")
    if not attr.meta_available:
        lines.append("*(skipped — no org context or meta.db data unavailable)*")
    else:
        lines.append(f"- Meta-informed posts: {attr.meta_informed_posts} of {attr.sable_posts} Sable posts")
        lines.append(f"- Meta-informed avg engagement: {attr.meta_informed_avg:.1f}")
        lines.append(f"- Non-meta-informed avg engagement: {attr.non_meta_informed_avg:.1f}")
        if attr.meta_lift is not None:
            lines.append(f"- Meta lift: {attr.meta_lift:+.0%}")
        else:
            lines.append("- Meta lift: insufficient data (need ≥2 posts in each group)")
    lines.append("")

    lines.append("## Weekly Trend")
    lines.append("| week | sable engagement | organic engagement | sable share |")
    lines.append("|------|-----------------|-------------------|-------------|")
    for w in attr.weekly_breakdown:
        lines.append(
            f"| {w['week']} | {w['sable']:.0f} | {w['organic']:.0f} | {w['share']:.0%} |"
        )

    return "\n".join(lines)
