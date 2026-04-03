"""Watchlist amplifier scoring — who spreads content vs passively consumes.

Three signals computed from existing scanned_tweets data:
  RT_v  = sum(reposts) / days_active
  RPR   = sum(replies) / total_engagement
  QTR   = sum(quotes) / total_tweets

Each signal is percentile-ranked within the org's watchlist. A weighted composite
produces the final amp_score.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sable import config as sable_cfg


# Default weights — override via config pulse_meta.amplifier_weights
W_RT_V = 0.40
W_RPR = 0.35
W_QTR = 0.25


@dataclass
class AmplifierRow:
    author: str
    rt_v: float
    rpr: float
    qtr: float
    amp_score: float
    rank: int


def _percentile_rank(values: list[float]) -> list[float]:
    """Percentile rank each value: fraction of values strictly less than this one."""
    n = len(values)
    if n <= 1:
        return [1.0] * n
    sorted_vals = sorted(values)
    rank_map: dict[float, float] = {}
    for i, v in enumerate(sorted_vals):
        if v not in rank_map:
            rank_map[v] = i / (n - 1)
    return [rank_map[v] for v in values]


def compute_amplifiers(
    org: str,
    window_days: int = 30,
    conn: sqlite3.Connection | None = None,
) -> list[AmplifierRow]:
    """Compute amplifier scores for all authors in an org's watchlist.

    Returns list sorted by amp_score descending.
    """
    if conn is None:
        from sable.pulse.meta.db import get_conn
        conn = get_conn()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    rows = conn.execute(
        """
        SELECT
            author_handle,
            COUNT(*) AS tweet_count,
            COUNT(DISTINCT date(posted_at)) AS days_active,
            COALESCE(SUM(reposts), 0) AS total_reposts,
            COALESCE(SUM(replies), 0) AS total_replies,
            COALESCE(SUM(quotes), 0) AS total_quotes,
            COALESCE(SUM(likes), 0) AS total_likes,
            COALESCE(SUM(bookmarks), 0) AS total_bookmarks
        FROM scanned_tweets
        WHERE org = ? AND posted_at >= ?
        GROUP BY author_handle
        """,
        (org, cutoff),
    ).fetchall()

    if not rows:
        return []

    # Load config weights (allow override)
    cfg = sable_cfg.load_config().get("pulse_meta", {})
    weights = cfg.get("amplifier_weights", {})
    w_rt = weights.get("rt_v", W_RT_V)
    w_rpr = weights.get("rpr", W_RPR)
    w_qtr = weights.get("qtr", W_QTR)

    # Compute raw signals per author
    authors: list[str] = []
    rt_vs: list[float] = []
    rprs: list[float] = []
    qtrs: list[float] = []

    for r in rows:
        authors.append(r["author_handle"])

        days_active = r["days_active"] or 1
        rt_vs.append(r["total_reposts"] / days_active)

        total_eng = (
            r["total_likes"]
            + r["total_reposts"]
            + r["total_replies"]
            + r["total_quotes"]
            + r["total_bookmarks"]
        )
        rprs.append(r["total_replies"] / total_eng if total_eng > 0 else 0.0)

        tweet_count = r["tweet_count"] or 1
        qtrs.append(r["total_quotes"] / tweet_count)

    # Percentile rank each signal
    rt_pctl = _percentile_rank(rt_vs)
    rpr_pctl = _percentile_rank(rprs)
    qtr_pctl = _percentile_rank(qtrs)

    # Composite score
    results: list[AmplifierRow] = []
    for i, author in enumerate(authors):
        amp = w_rt * rt_pctl[i] + w_rpr * rpr_pctl[i] + w_qtr * qtr_pctl[i]
        results.append(
            AmplifierRow(
                author=author,
                rt_v=round(rt_vs[i], 4),
                rpr=round(rprs[i], 4),
                qtr=round(qtrs[i], 4),
                amp_score=round(amp, 4),
                rank=0,
            )
        )

    # Sort descending by amp_score, assign ranks
    results.sort(key=lambda r: r.amp_score, reverse=True)
    for i, r in enumerate(results):
        r.rank = i + 1

    return results
