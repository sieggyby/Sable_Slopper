"""Combine cadence signals into silence gradient score."""
from __future__ import annotations

import logging
import sqlite3
import statistics
from datetime import datetime, timedelta, timezone

from sable.cadence.signals import (
    compute_volume_drop,
    compute_engagement_drop,
    compute_format_regression,
    MIN_ROWS_PER_HALF,
)

logger = logging.getLogger(__name__)

# Default weights (sum to 1.0)
W_VOL = 0.40
W_ENG = 0.35
W_FMT = 0.25

# Minimum window_days (split into two halves)
MIN_WINDOW_DAYS = 6


def compute_silence_gradient(
    org: str,
    window_days: int = 30,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """Compute silence gradient for all authors in an org.

    Splits window into two equal halves (recent vs prior).
    Returns list of dicts sorted by silence_gradient desc.
    Authors where all three signals are insufficient are excluded.
    """
    if window_days < MIN_WINDOW_DAYS:
        raise ValueError(f"window_days must be >= {MIN_WINDOW_DAYS}, got {window_days}")
    if window_days % 2 != 0:
        raise ValueError(f"window_days must be even, got {window_days}")

    if conn is None:
        from sable.pulse.meta.db import get_conn
        conn = get_conn()

    now = datetime.now(timezone.utc)
    half = window_days // 2
    recent_cutoff = (now - timedelta(days=half)).strftime("%Y-%m-%d %H:%M:%S")
    prior_cutoff = (now - timedelta(days=window_days)).strftime("%Y-%m-%d %H:%M:%S")

    # Get all authors with tweets in the window
    rows = conn.execute(
        """SELECT author_handle, posted_at, total_lift, format_bucket
           FROM scanned_tweets
           WHERE org = ? AND posted_at >= ?
           ORDER BY author_handle, posted_at""",
        (org, prior_cutoff),
    ).fetchall()

    # Group by author
    author_data: dict[str, list[dict]] = {}
    for r in rows:
        handle = r["author_handle"]
        author_data.setdefault(handle, []).append(dict(r))

    results: list[dict] = []
    for handle, tweets in author_data.items():
        recent = [t for t in tweets if t["posted_at"] >= recent_cutoff]
        prior = [t for t in tweets if t["posted_at"] < recent_cutoff]

        # Volume drop
        vol_score, vol_insuf = compute_volume_drop(len(recent), len(prior))

        # Engagement drop (median total_lift)
        recent_lifts = [t["total_lift"] for t in recent if t["total_lift"] is not None]
        prior_lifts = [t["total_lift"] for t in prior if t["total_lift"] is not None]
        med_recent = statistics.median(recent_lifts) if recent_lifts else 0.0
        med_prior = statistics.median(prior_lifts) if prior_lifts else 0.0
        eng_score, eng_insuf = compute_engagement_drop(
            med_recent, med_prior, len(recent_lifts), len(prior_lifts)
        )

        # Format regression (recent half only)
        fmt_counts: dict[str, int] = {}
        for t in recent:
            b = t.get("format_bucket") or "unknown"
            fmt_counts[b] = fmt_counts.get(b, 0) + 1
        fmt_score, fmt_insuf = compute_format_regression(fmt_counts)

        # Combine with proportional weight redistribution
        signals = [
            (W_VOL, vol_score, vol_insuf),
            (W_ENG, eng_score, eng_insuf),
            (W_FMT, fmt_score, fmt_insuf),
        ]
        sufficient = [(w, s) for w, s, insuf in signals if not insuf]
        if not sufficient:
            continue  # All insufficient → exclude

        total_weight = sum(w for w, _ in sufficient)
        gradient = sum(w * s / total_weight for w, s in sufficient)

        insufficient_list = []
        if vol_insuf:
            insufficient_list.append("volume")
        if eng_insuf:
            insufficient_list.append("engagement")
        if fmt_insuf:
            insufficient_list.append("format")

        results.append({
            "author_handle": handle,
            "org": org,
            "posts_recent_half": len(recent),
            "posts_prior_half": len(prior),
            "median_lift_recent": round(med_recent, 4),
            "median_lift_prior": round(med_prior, 4),
            "vol_drop": round(vol_score, 4),
            "eng_drop": round(eng_score, 4),
            "fmt_reg": round(fmt_score, 4),
            "silence_gradient": round(gradient, 4),
            "insufficient_data": ",".join(insufficient_list) if insufficient_list else None,
            "window_days": window_days,
        })

    results.sort(key=lambda r: r["silence_gradient"], reverse=True)
    return results
