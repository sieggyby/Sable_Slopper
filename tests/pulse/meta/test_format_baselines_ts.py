"""Tests for format_baselines time-series migration (Slice A)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from sable.pulse.meta.db import _SCHEMA, get_format_baselines_as_of, prune_format_baselines


def _make_mem_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _ts(days_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _insert_baseline(conn: sqlite3.Connection, org: str, bucket: str,
                     period_days: int, avg_lift: float, computed_at: str) -> None:
    conn.execute(
        """INSERT INTO format_baselines
           (org, format_bucket, period_days, avg_total_lift, sample_count, unique_authors, computed_at)
           VALUES (?, ?, ?, ?, 10, 5, ?)""",
        (org, bucket, period_days, avg_lift, computed_at),
    )
    conn.commit()


def test_upsert_accumulates_rows():
    """Two inserts for the same bucket produce 2 rows (not 1)."""
    conn = _make_mem_db()
    _insert_baseline(conn, "org1", "short_clip", 7, 1.5, _ts(2))
    _insert_baseline(conn, "org1", "short_clip", 7, 2.0, _ts(0))
    count = conn.execute(
        "SELECT COUNT(*) FROM format_baselines WHERE org='org1' AND format_bucket='short_clip'"
    ).fetchone()[0]
    assert count == 2


def test_get_format_baselines_as_of_returns_correct_row():
    """as_of=t1 returns t1 row; as_of=t2 returns t2 row."""
    conn = _make_mem_db()
    t1 = _ts(5)
    t2 = _ts(1)
    _insert_baseline(conn, "org1", "short_clip", 7, 1.0, t1)
    _insert_baseline(conn, "org1", "short_clip", 7, 2.0, t2)

    rows_at_t1 = get_format_baselines_as_of("org1", t1, period_days=7, conn=conn)
    assert len(rows_at_t1) == 1
    assert rows_at_t1[0]["avg_total_lift"] == pytest.approx(1.0)

    rows_at_t2 = get_format_baselines_as_of("org1", t2, period_days=7, conn=conn)
    assert len(rows_at_t2) == 1
    assert rows_at_t2[0]["avg_total_lift"] == pytest.approx(2.0)


def test_get_format_baselines_as_of_empty_when_all_future():
    """Row at t2 (future relative to t1); calling with as_of=t1 returns empty list."""
    conn = _make_mem_db()
    t1 = _ts(5)
    t2 = _ts(1)
    _insert_baseline(conn, "org1", "short_clip", 7, 2.0, t2)

    rows = get_format_baselines_as_of("org1", t1, period_days=7, conn=conn)
    assert rows == []


def test_prune_keeps_most_recent_n():
    """5 rows for same bucket; prune(keep_n=3) → 3 rows remain, oldest 2 gone."""
    conn = _make_mem_db()
    times = [_ts(i) for i in range(4, -1, -1)]  # oldest first
    for i, ts in enumerate(times):
        _insert_baseline(conn, "org1", "short_clip", 7, float(i), ts)

    prune_format_baselines("org1", keep_n=3, conn=conn)

    rows = conn.execute(
        "SELECT computed_at FROM format_baselines WHERE org='org1' AND format_bucket='short_clip' "
        "ORDER BY computed_at ASC"
    ).fetchall()
    assert len(rows) == 3
    # The 3 most recent should remain; oldest 2 gone
    remaining_times = [r["computed_at"] for r in rows]
    assert times[0] not in remaining_times  # oldest gone
    assert times[1] not in remaining_times  # second oldest gone
