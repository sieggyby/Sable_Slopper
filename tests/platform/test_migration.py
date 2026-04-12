"""Test schema migration."""
import sqlite3

from sable.platform.db import ensure_schema
from sable_platform.db.connection import _MIGRATIONS

EXPECTED_VERSION = _MIGRATIONS[-1][1]


def test_schema_version_is_current(migration_conn):
    row = migration_conn.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == EXPECTED_VERSION


def test_all_tables_exist(migration_conn):
    expected_tables = {
        "schema_version", "orgs", "entities", "entity_handles", "entity_tags",
        "entity_notes", "merge_candidates", "merge_events", "content_items",
        "diagnostic_runs", "jobs", "job_steps", "artifacts", "cost_events", "sync_runs",
        "discord_pulse_runs",
    }
    rows = migration_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    found = {r["name"] for r in rows}
    assert expected_tables.issubset(found)


def test_ensure_schema_idempotent(migration_conn):
    """Calling ensure_schema again on a migrated DB must not error or change version."""
    ensure_schema(migration_conn)
    row = migration_conn.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == EXPECTED_VERSION


def test_ensure_schema_on_fresh_db():
    """ensure_schema works on a brand-new in-memory connection."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_schema(c)
    row = c.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == EXPECTED_VERSION
    c.close()


def test_jobs_extended_columns(migration_conn):
    """Migration 004: jobs table has completed_at, result_json, error_message."""
    cols = {row[1] for row in migration_conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "completed_at" in cols
    assert "result_json" in cols
    assert "error_message" in cols
