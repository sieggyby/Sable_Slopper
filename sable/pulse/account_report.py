"""Account-level format lift computation for `sable pulse account`.

Reads pulse.db (posts + snapshots) and optionally meta.db (niche baselines)
to produce a per-format lift report for a managed account.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Optional

import logging

from sable.pulse.meta.fingerprint import classify_format
from sable.shared.handles import ensure_handle_prefix as _norm_handle, strip_handle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FormatLiftEntry:
    format_bucket: str
    account_lift: Optional[float]         # None = insufficient data (< 2 posts)
    niche_lift: Optional[float]           # None = no niche data available
    niche_trend_status: Optional[str]     # None = no niche data available
    niche_confidence: Optional[str]       # None = no niche data available
    post_count: int
    divergence_signal: str  # DOUBLE DOWN / EXECUTION GAP / ACCOUNT DIFFERENTIATION / AVOID / NEUTRAL


@dataclass
class AccountFormatReport:
    handle: str
    org: str
    days: int
    total_posts: int
    entries: list[FormatLiftEntry]
    missing_niche_formats: list[str]  # formats surging in niche but never used by account
    generated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engagement_score(row: dict) -> float:
    """Compute weighted engagement from a snapshot row (or zero if no snapshot)."""
    likes = row.get("likes") or 0
    retweets = row.get("retweets") or 0
    replies = row.get("replies") or 0
    views = row.get("views") or 0
    bookmarks = row.get("bookmarks") or 0
    quotes = row.get("quotes") or 0
    return likes + 3 * replies + 4 * retweets + 5 * quotes + 2 * bookmarks + 0.5 * views


def _classify_post(post: dict) -> str:
    """Map a pulse.db post row to a format_bucket string.

    Posts use sable_content_type ('clip', 'meme', etc.), not the pulse-meta
    format buckets directly. Maps deterministically per the spec; for 'text' and
    'unknown' types, delegates to classify_format() with minimal tweet-dict.
    """
    ct = (post.get("sable_content_type") or "unknown").lower()
    if ct == "clip":
        return "short_clip"  # default; long_clip requires duration from sidecar
    if ct == "meme":
        return "single_image"
    if ct == "explainer":
        return "long_clip"
    if ct == "faceswap":
        return "short_clip"
    # 'text', 'unknown', or anything else: delegate to classify_format with no media flags
    return classify_format(
        is_quote_tweet=False,
        is_thread=False,
        thread_length=1,
        has_video=False,
        video_duration=None,
        has_image=False,
        has_link=False,
        urls=[],
    )


def _compute_account_baseline(posts: list[dict]) -> float:
    """Compute median engagement across all posts. Returns 1.0 as floor to avoid /0."""
    scores = [_engagement_score(p) for p in posts]
    if not scores:
        return 1.0
    m = median(scores)
    return max(1.0, m)


def _divergence_signal(
    account_lift: Optional[float],
    niche_lift: Optional[float],
) -> str:
    """Classify divergence between account performance and niche baseline."""
    if account_lift is None or niche_lift is None:
        return "NEUTRAL"
    if account_lift >= 1.5 and niche_lift >= 1.5:
        return "DOUBLE DOWN"
    if account_lift <= 0.8 and niche_lift >= 1.5:
        return "EXECUTION GAP"
    if account_lift >= 1.5 and niche_lift <= 0.8:
        return "ACCOUNT DIFFERENTIATION"
    if account_lift <= 0.8 and niche_lift <= 0.8:
        return "AVOID"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Pulse.db reader
# ---------------------------------------------------------------------------

def _load_posts_with_snapshots(
    conn: sqlite3.Connection,
    handle: str,
    since_iso: str,
) -> list[dict]:
    """Load posts + most-recent snapshot for each post in the window."""
    rows = conn.execute(
        """
        SELECT p.id, p.text, p.posted_at, p.sable_content_type,
               s.likes, s.retweets, s.replies, s.views, s.bookmarks, s.quotes
        FROM posts p
        LEFT JOIN snapshots s ON (
            p.id = s.post_id
            AND s.id = (
                SELECT MAX(s2.id) FROM snapshots s2 WHERE s2.post_id = p.id
            )
        )
        WHERE p.account_handle = ? AND p.posted_at >= ?
        ORDER BY p.posted_at DESC
        """,
        (handle, since_iso),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Niche baseline loader
# ---------------------------------------------------------------------------

def _load_niche_lifts(
    meta_db_path: Optional[Path],
    org: str,
    days: int,
) -> dict[str, dict]:
    """Load niche format lift data from meta.db for divergence analysis."""
    if not meta_db_path or not meta_db_path.exists() or not org:
        return {}
    try:
        import json as _json
        from sable.pulse.meta.baselines import _rows_to_normalized
        from sable.pulse.meta.trends import analyze_all_formats, TrendResult
        from sable.pulse.meta.normalize import AuthorNormalizedTweet

        conn = sqlite3.connect(str(meta_db_path))
        conn.row_factory = sqlite3.Row
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        raw_rows = conn.execute(
            """SELECT * FROM scanned_tweets
               WHERE org = ? AND posted_at >= ? AND total_lift IS NOT NULL
               ORDER BY posted_at DESC""",
            (org, since),
        ).fetchall()
        conn.close()

        if not raw_rows:
            return {}

        # Parse attributes_json → attributes (required by _rows_to_normalized)
        rows: list[dict] = []
        for row in raw_rows:
            d = dict(row)
            d["attributes"] = _json.loads(d.get("attributes_json") or "[]")
            rows.append(d)

        normalized: list[AuthorNormalizedTweet] = _rows_to_normalized(rows)
        if not normalized:
            return {}

        # Group by format_bucket
        tweets_by_bucket: dict[str, list[AuthorNormalizedTweet]] = {}
        for tweet in normalized:
            tweets_by_bucket.setdefault(tweet.format_bucket, []).append(tweet)

        # Pass (None, None) baselines — current_lift is computed from tweet data;
        # trend_status/momentum will be None (no baseline comparison), which is acceptable.
        empty_baselines: dict[str, tuple[Optional[float], Optional[float]]] = {
            b: (None, None) for b in tweets_by_bucket
        }
        trend_results: dict[str, TrendResult] = analyze_all_formats(
            org=org,
            tweets_by_bucket=tweets_by_bucket,
            baselines=empty_baselines,
            baseline_days_available=0,
        )
        return {
            bucket: {
                "current_lift": tr.current_lift,
                "trend_status": tr.trend_status,
                "confidence": tr.confidence,
            }
            for bucket, tr in trend_results.items()
        }
    except Exception as e:
        logger.warning("_load_niche_lifts failed for org=%r: %s", org, e, exc_info=True)
        return {}


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_account_format_lift(
    handle: str,
    org: str,
    days: int,
    pulse_db_path: Path,
    meta_db_path: Optional[Path] = None,
) -> AccountFormatReport:
    """Compute per-format lift for a managed account's own posting history.

    Args:
        handle: Twitter handle (with or without @).
        org: Org string for niche divergence analysis (may be "").
        days: Lookback window in days.
        pulse_db_path: Path to pulse.db.
        meta_db_path: Optional path to meta.db for niche baselines.

    Returns:
        AccountFormatReport with per-format lift entries.
    """
    norm = _norm_handle(handle)
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since_iso = since_dt.isoformat()

    conn = sqlite3.connect(str(pulse_db_path))
    conn.row_factory = sqlite3.Row

    posts = _load_posts_with_snapshots(conn, norm, since_iso)
    conn.close()

    total_posts = len(posts)
    baseline = _compute_account_baseline(posts)

    # Group posts by format bucket
    by_bucket: dict[str, list[dict]] = {}
    for post in posts:
        bucket = _classify_post(post)
        by_bucket.setdefault(bucket, []).append(post)

    # Load niche data (empty dict if meta_db_path not available)
    niche_data = _load_niche_lifts(meta_db_path, org, days) if org else {}

    account_buckets = set(by_bucket.keys())
    niche_surging = {
        b for b, nd in niche_data.items()
        if nd.get("current_lift") is not None and nd["current_lift"] >= 1.5
    }
    missing_niche_formats = sorted(niche_surging - account_buckets)

    entries: list[FormatLiftEntry] = []
    # Build entries for all buckets seen in account posts
    for bucket, bucket_posts in sorted(by_bucket.items()):
        count = len(bucket_posts)
        if count >= 2:
            scores = [_engagement_score(p) for p in bucket_posts]
            mean_score = sum(scores) / len(scores)
            account_lift = mean_score / baseline
        else:
            account_lift = None

        nd = niche_data.get(bucket, {})
        niche_lift = nd.get("current_lift")
        niche_trend_status = nd.get("trend_status")
        niche_confidence = nd.get("confidence")

        signal = _divergence_signal(account_lift, niche_lift)

        entries.append(FormatLiftEntry(
            format_bucket=bucket,
            account_lift=account_lift,
            niche_lift=niche_lift,
            niche_trend_status=niche_trend_status,
            niche_confidence=niche_confidence,
            post_count=count,
            divergence_signal=signal,
        ))

    # Sort entries: sufficient data first (by account_lift desc), then insufficient
    entries.sort(
        key=lambda e: (e.account_lift is None, -(e.account_lift or 0))
    )

    return AccountFormatReport(
        handle=norm,
        org=org,
        days=days,
        total_posts=total_posts,
        entries=entries,
        missing_niche_formats=missing_niche_formats,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

_BAR_CHAR = "█"
_BAR_WIDTH = 12  # max bar width at 3.0x lift


def _lift_bar(lift: float) -> str:
    """Render a simple ASCII bar proportional to lift (capped at 3.0x)."""
    filled = min(int(lift / 3.0 * _BAR_WIDTH), _BAR_WIDTH)
    return _BAR_CHAR * filled


def render_account_report(report: AccountFormatReport) -> str:
    """Return a formatted console string for the account report."""
    org_label = f", org: {report.org}" if report.org else ""
    header = (
        f"@{strip_handle(report.handle)} — Format Lift "
        f"(last {report.days}d, {report.total_posts} posts{org_label})\n"
    )
    lines: list[str] = [header]

    for entry in report.entries:
        bucket = entry.format_bucket
        if entry.account_lift is not None:
            bar = _lift_bar(entry.account_lift)
            acc_str = f"{entry.account_lift:.1f}x"
            if entry.niche_lift is not None:
                niche_str = f"niche: {entry.niche_lift:.1f}x"
                line = f"  {bucket:<18} {bar:<{_BAR_WIDTH}}  {acc_str}  {niche_str}  → {entry.divergence_signal}"
            else:
                line = f"  {bucket:<18} {bar:<{_BAR_WIDTH}}  {acc_str}"
        else:
            line = f"  {bucket:<18} [insufficient data: {entry.post_count} post{'s' if entry.post_count != 1 else ''}]"
        lines.append(line)

    if report.entries:
        top = [e for e in report.entries if e.account_lift is not None]
        if top:
            top_str = ", ".join(
                f"{e.format_bucket} ({e.account_lift:.1f}x)" for e in top[:3]
            )
            lines.append(f"\n  Top formats by account lift: {top_str}")

    if report.missing_niche_formats:
        lines.append(
            f"  Niche surging but unused by this account: {', '.join(report.missing_niche_formats)}"
        )

    return "\n".join(lines) + "\n"
