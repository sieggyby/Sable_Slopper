"""Test schema migration."""
import sqlite3

from sable.platform.db import ensure_schema


def test_schema_version_is_current(conn):
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == 5


def test_all_tables_exist(conn):
    expected_tables = {
        "schema_version", "orgs", "entities", "entity_handles", "entity_tags",
        "entity_notes", "merge_candidates", "merge_events", "content_items",
        "diagnostic_runs", "jobs", "job_steps", "artifacts", "cost_events", "sync_runs",
    }
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    found = {r["name"] for r in rows}
    assert expected_tables.issubset(found)


def test_ensure_schema_idempotent(conn):
    """Calling ensure_schema again on a migrated DB must not error or change version."""
    ensure_schema(conn)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == 5


def test_ensure_schema_on_fresh_db():
    """ensure_schema works on a brand-new in-memory connection."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_schema(c)
    row = c.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == 5
    c.close()


def test_jobs_extended_columns(conn):
    """Migration 004: jobs table has completed_at, result_json, error_message."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "completed_at" in cols
    assert "result_json" in cols
    assert "error_message" in cols
