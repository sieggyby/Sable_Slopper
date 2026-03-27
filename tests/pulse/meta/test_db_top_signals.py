"""Tests for get_top_topic_signals in sable.pulse.meta.db."""
from __future__ import annotations

import sqlite3
import pytest

from sable.pulse.meta.db import _SCHEMA


class _NoClose:
    """Proxy that makes close() a no-op so the in-memory DB stays alive."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.row_factory = conn.row_factory

    def execute(self, *a, **kw):
        return self._conn.execute(*a, **kw)

    def executemany(self, *a, **kw):
        return self._conn.executemany(*a, **kw)

    def executescript(self, *a, **kw):
        return self._conn.executescript(*a, **kw)

    def commit(self):
        return self._conn.commit()

    def close(self):
        pass

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *a):
        return self._conn.__exit__(*a)


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _insert_scan_run(conn, org, completed=True, failed=False, scan_id=None):
    """Insert a scan_run and return its id."""
    if failed:
        claude_raw = "FAILED: something went wrong"
    else:
        claude_raw = None
    completed_at = "2026-01-01 12:00:00" if completed else None
    cursor = conn.execute(
        """INSERT INTO scan_runs (org, started_at, completed_at, mode, claude_raw)
           VALUES (?, '2026-01-01 11:00:00', ?, 'full', ?)""",
        (org, completed_at, claude_raw),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_signal(conn, org, scan_id, term, avg_lift, acceleration, unique_authors, mention_count):
    conn.execute(
        """INSERT INTO topic_signals (org, scan_id, term, mention_count, unique_authors,
           avg_lift, prev_scan_mentions, acceleration)
           VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
        (org, scan_id, term, mention_count, unique_authors, avg_lift, acceleration),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_returns_signals_from_latest_scan_only(monkeypatch):
    """Signals from the latest completed scan only, not older scans."""
    from sable.pulse.meta.db import get_top_topic_signals

    conn = _make_conn()
    proxy = _NoClose(conn)

    old_id = _insert_scan_run(conn, "testorg")
    _insert_signal(conn, "testorg", old_id, "old_term", 3.0, 1.5, 5, 10)

    new_id = _insert_scan_run(conn, "testorg")
    _insert_signal(conn, "testorg", new_id, "new_term", 2.0, 2.0, 3, 6)

    monkeypatch.setattr("sable.pulse.meta.db.get_conn", lambda: proxy)
    results = get_top_topic_signals("testorg", conn=proxy)

    terms = [r["term"] for r in results]
    assert "new_term" in terms
    assert "old_term" not in terms


def test_failed_scan_excluded_uses_prior_good_scan(monkeypatch):
    """A FAILED scan is excluded; falls back to the prior good scan."""
    from sable.pulse.meta.db import get_top_topic_signals

    conn = _make_conn()
    proxy = _NoClose(conn)

    good_id = _insert_scan_run(conn, "testorg")
    _insert_signal(conn, "testorg", good_id, "good_term", 2.0, 1.0, 2, 5)

    failed_id = _insert_scan_run(conn, "testorg", failed=True)
    _insert_signal(conn, "testorg", failed_id, "bad_term", 9.9, 9.9, 99, 99)

    monkeypatch.setattr("sable.pulse.meta.db.get_conn", lambda: proxy)
    results = get_top_topic_signals("testorg", conn=proxy)

    terms = [r["term"] for r in results]
    assert "good_term" in terms
    assert "bad_term" not in terms


def test_empty_org_returns_empty_list(monkeypatch):
    """An org with no scan runs returns []."""
    from sable.pulse.meta.db import get_top_topic_signals

    conn = _make_conn()
    proxy = _NoClose(conn)

    monkeypatch.setattr("sable.pulse.meta.db.get_conn", lambda: proxy)
    results = get_top_topic_signals("ghostorg", conn=proxy)
    assert results == []


def test_min_unique_authors_filter(monkeypatch):
    """Signals with unique_authors < min_unique_authors are excluded."""
    from sable.pulse.meta.db import get_top_topic_signals

    conn = _make_conn()
    proxy = _NoClose(conn)

    scan_id = _insert_scan_run(conn, "testorg")
    _insert_signal(conn, "testorg", scan_id, "popular_term", 2.0, 1.0, 5, 10)
    _insert_signal(conn, "testorg", scan_id, "lone_term", 2.0, 1.0, 1, 3)

    monkeypatch.setattr("sable.pulse.meta.db.get_conn", lambda: proxy)
    results = get_top_topic_signals("testorg", min_unique_authors=2, conn=proxy)

    terms = [r["term"] for r in results]
    assert "popular_term" in terms
    assert "lone_term" not in terms


def test_sorted_by_score_descending(monkeypatch):
    """Results are sorted by avg_lift * acceleration * unique_authors desc."""
    from sable.pulse.meta.db import get_top_topic_signals

    conn = _make_conn()
    proxy = _NoClose(conn)

    scan_id = _insert_scan_run(conn, "testorg")
    # score = avg_lift * acceleration * unique_authors
    # low: 1.0 * 1.0 * 1 = 1.0
    # high: 3.0 * 2.0 * 4 = 24.0
    # mid: 2.0 * 1.5 * 3 = 9.0
    _insert_signal(conn, "testorg", scan_id, "low_term", 1.0, 1.0, 1, 2)
    _insert_signal(conn, "testorg", scan_id, "high_term", 3.0, 2.0, 4, 8)
    _insert_signal(conn, "testorg", scan_id, "mid_term", 2.0, 1.5, 3, 6)

    monkeypatch.setattr("sable.pulse.meta.db.get_conn", lambda: proxy)
    results = get_top_topic_signals("testorg", conn=proxy)

    terms = [r["term"] for r in results]
    assert terms == ["high_term", "mid_term", "low_term"]


def test_result_dict_has_expected_keys(monkeypatch):
    """Each result dict has term, avg_lift, acceleration, unique_authors, mention_count."""
    from sable.pulse.meta.db import get_top_topic_signals

    conn = _make_conn()
    proxy = _NoClose(conn)

    scan_id = _insert_scan_run(conn, "testorg")
    _insert_signal(conn, "testorg", scan_id, "defi", 2.0, 1.5, 3, 7)

    monkeypatch.setattr("sable.pulse.meta.db.get_conn", lambda: proxy)
    results = get_top_topic_signals("testorg", conn=proxy)

    assert len(results) == 1
    r = results[0]
    assert set(r.keys()) >= {"term", "avg_lift", "acceleration", "unique_authors", "mention_count"}
    assert r["term"] == "defi"
    assert r["avg_lift"] == 2.0
    assert r["acceleration"] == 1.5
    assert r["unique_authors"] == 3
    assert r["mention_count"] == 7
