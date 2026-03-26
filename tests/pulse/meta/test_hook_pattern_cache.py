"""DB-layer tests for hook_pattern_cache helpers in sable.pulse.meta.db."""
from __future__ import annotations

import json
import sqlite3

import pytest


class _NoClose:
    """Proxy that makes close() a no-op so monkeypatched get_conn() stays open."""
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
        pass  # no-op — keep the in-memory DB alive across helper calls

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *a):
        return self._conn.__exit__(*a)


def _make_conn() -> sqlite3.Connection:
    """In-memory meta.db with the tables needed for hook pattern cache tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE hook_pattern_cache (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            org           TEXT NOT NULL,
            format_bucket TEXT NOT NULL,
            patterns_json TEXT NOT NULL,
            generated_at  TEXT NOT NULL
        );
        CREATE UNIQUE INDEX idx_hook_patterns_key
            ON hook_pattern_cache (org, format_bucket);

        CREATE TABLE scan_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            org          TEXT NOT NULL,
            started_at   TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            mode         TEXT,
            tweets_collected INTEGER DEFAULT 0,
            tweets_new       INTEGER DEFAULT 0,
            estimated_cost   REAL,
            watchlist_size   INTEGER DEFAULT 0,
            claude_raw   TEXT
        );
    """)
    return conn


# --- upsert_hook_patterns / get_hook_patterns_cache ---

def test_upsert_stores_patterns(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    db_mod.upsert_hook_patterns("testorg", "standalone_text", json.dumps([{"name": "p1"}]))

    row = conn.execute(
        "SELECT * FROM hook_pattern_cache WHERE org='testorg' AND format_bucket='standalone_text'"
    ).fetchone()
    assert row is not None
    assert json.loads(row["patterns_json"]) == [{"name": "p1"}]
    assert row["generated_at"] is not None


def test_get_hook_patterns_cache_returns_none_when_empty(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    result = db_mod.get_hook_patterns_cache("testorg", "standalone_text")
    assert result is None


def test_get_hook_patterns_cache_returns_row(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    db_mod.upsert_hook_patterns("testorg", "standalone_text", json.dumps([{"name": "p1"}]))
    result = db_mod.get_hook_patterns_cache("testorg", "standalone_text")

    assert result is not None
    assert result["org"] == "testorg"
    assert result["format_bucket"] == "standalone_text"
    assert json.loads(result["patterns_json"]) == [{"name": "p1"}]


def test_upsert_overwrites_existing(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    db_mod.upsert_hook_patterns("testorg", "standalone_text", json.dumps([{"name": "old"}]))
    db_mod.upsert_hook_patterns("testorg", "standalone_text", json.dumps([{"name": "new"}]))

    result = db_mod.get_hook_patterns_cache("testorg", "standalone_text")
    assert json.loads(result["patterns_json"]) == [{"name": "new"}]
    count = conn.execute("SELECT COUNT(*) FROM hook_pattern_cache").fetchone()[0]
    assert count == 1  # no duplicate rows


def test_cache_is_keyed_by_org_and_format(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    db_mod.upsert_hook_patterns("org_a", "standalone_text", json.dumps([{"name": "a"}]))
    db_mod.upsert_hook_patterns("org_b", "standalone_text", json.dumps([{"name": "b"}]))
    db_mod.upsert_hook_patterns("org_a", "short_clip", json.dumps([{"name": "c"}]))

    assert json.loads(db_mod.get_hook_patterns_cache("org_a", "standalone_text")["patterns_json"]) == [{"name": "a"}]
    assert json.loads(db_mod.get_hook_patterns_cache("org_b", "standalone_text")["patterns_json"]) == [{"name": "b"}]
    assert json.loads(db_mod.get_hook_patterns_cache("org_a", "short_clip")["patterns_json"]) == [{"name": "c"}]


# --- get_latest_successful_scan_at ---

def test_get_latest_successful_scan_at_returns_none_when_empty(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    assert db_mod.get_latest_successful_scan_at("testorg") is None


def test_get_latest_successful_scan_at_returns_timestamp(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    conn.execute(
        "INSERT INTO scan_runs (org, completed_at, claude_raw) VALUES (?, ?, ?)",
        ("testorg", "2026-03-25 10:00:00", "some output"),
    )
    conn.commit()

    result = db_mod.get_latest_successful_scan_at("testorg")
    assert result == "2026-03-25 10:00:00"


def test_get_latest_successful_scan_at_ignores_failed_scans(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    conn.executemany(
        "INSERT INTO scan_runs (org, completed_at, claude_raw) VALUES (?, ?, ?)",
        [
            ("testorg", "2026-03-25 12:00:00", "FAILED: rate limit"),
            ("testorg", "2026-03-25 09:00:00", "good output"),
        ],
    )
    conn.commit()

    result = db_mod.get_latest_successful_scan_at("testorg")
    assert result == "2026-03-25 09:00:00"  # failed scan skipped


def test_get_latest_successful_scan_at_returns_most_recent(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    conn.executemany(
        "INSERT INTO scan_runs (org, completed_at, claude_raw) VALUES (?, ?, ?)",
        [
            ("testorg", "2026-03-25 09:00:00", "good output"),
            ("testorg", "2026-03-25 11:00:00", "good output"),
            ("testorg", "2026-03-25 10:00:00", "good output"),
        ],
    )
    conn.commit()

    result = db_mod.get_latest_successful_scan_at("testorg")
    assert result == "2026-03-25 11:00:00"


def test_get_latest_successful_scan_at_ignores_other_orgs(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    conn.execute(
        "INSERT INTO scan_runs (org, completed_at, claude_raw) VALUES (?, ?, ?)",
        ("other_org", "2026-03-25 10:00:00", "good output"),
    )
    conn.commit()

    assert db_mod.get_latest_successful_scan_at("testorg") is None
