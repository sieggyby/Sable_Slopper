"""Sync content performance outcomes from pulse.db to sable.db."""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict

logger = logging.getLogger(__name__)


def sync_content_outcomes(
    org_id: str,
    handle: str,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Read pulse.db posts+snapshots, write outcomes to sable.db.

    Groups posts by sable_content_type, computes per-type average engagement
    rate (view-normalised), and records one outcome per type plus an aggregate.

    Returns count of outcome rows created.
    """
    from sable.pulse.db import get_posts_for_account, get_latest_snapshot

    posts = get_posts_for_account(handle, limit=200)
    if not posts:
        return 0

    # Group posts by content type and collect latest snapshots
    by_type: dict[str, list[dict]] = defaultdict(list)
    for post in posts:
        snap = get_latest_snapshot(post["id"])
        if not snap:
            continue
        ct = post.get("sable_content_type") or "unknown"
        snap["sable_content_type"] = ct
        by_type[ct].append(snap)

    if not by_type:
        return 0

    close_conn = False
    if conn is None:
        from sable.platform.db import get_db
        conn = get_db()
        close_conn = True

    try:
        from sable.platform.outcomes import create_outcome, list_outcomes

        # Build lookup of most recent metric_after values (one query, not N)
        prior_rows = list_outcomes(
            conn, org_id, outcome_type="content_performance", limit=200,
        )
        prior_by_name: dict[str, float] = {}
        for row in prior_rows:
            name = row["metric_name"]
            if name not in prior_by_name and row["metric_after"] is not None:
                prior_by_name[name] = row["metric_after"]

        created = 0
        all_rates: list[float] = []

        for content_type, snaps in sorted(by_type.items()):
            rates = []
            for s in snaps:
                views = s.get("views", 0) or 0
                eng = (s.get("likes", 0) + s.get("retweets", 0)
                       + s.get("replies", 0) + s.get("quotes", 0))
                rate = eng / max(views, 1)
                rates.append(rate)
            avg_rate = sum(rates) / len(rates) if rates else 0.0
            all_rates.extend(rates)

            metric_name = f"engagement_rate_{content_type}"
            create_outcome(
                conn, org_id, "content_performance",
                metric_name=metric_name,
                metric_before=prior_by_name.get(metric_name),
                metric_after=round(avg_rate, 6),
                data_json=json.dumps({
                    "handle": handle,
                    "content_type": content_type,
                    "post_count": len(snaps),
                }),
                recorded_by="pulse_outcomes",
            )
            created += 1

        # Aggregate across all types
        if all_rates:
            overall = sum(all_rates) / len(all_rates)
            create_outcome(
                conn, org_id, "content_performance",
                metric_name="engagement_rate_overall",
                metric_before=prior_by_name.get("engagement_rate_overall"),
                metric_after=round(overall, 6),
                data_json=json.dumps({
                    "handle": handle,
                    "total_posts": sum(len(s) for s in by_type.values()),
                    "content_types": sorted(by_type.keys()),
                }),
                recorded_by="pulse_outcomes",
            )
            created += 1

        return created
    finally:
        if close_conn:
            conn.close()
