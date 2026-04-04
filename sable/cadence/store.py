"""Persistence for cadence / silence gradient results."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def upsert_cadence(rows: list[dict], conn: sqlite3.Connection) -> int:
    """INSERT OR REPLACE cadence rows. Returns count written."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    with conn:
        for r in rows:
            conn.execute(
                """INSERT OR REPLACE INTO author_cadence
                   (author_handle, org, computed_at,
                    posts_recent_half, posts_prior_half,
                    median_lift_recent, median_lift_prior,
                    vol_drop, eng_drop, fmt_reg,
                    silence_gradient, insufficient_data, window_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r["author_handle"], r["org"], now,
                    r["posts_recent_half"], r["posts_prior_half"],
                    r["median_lift_recent"], r["median_lift_prior"],
                    r["vol_drop"], r["eng_drop"], r["fmt_reg"],
                    r["silence_gradient"], r.get("insufficient_data"),
                    r["window_days"],
                ),
            )
            count += 1
    return count
