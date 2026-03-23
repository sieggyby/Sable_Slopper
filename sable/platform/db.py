"""Shared SQLite connection factory and migration runner for sable.db."""
from __future__ import annotations

import sqlite3
from pathlib import Path

_MIGRATIONS = [
    ("001_initial.sql", 1),
    ("002_sync_runs_run_id.sql", 2),
    ("003_diagnostic_runs_cult_columns.sql", 3),
    ("004_jobs_extend.sql", 4),
]


def get_db() -> sqlite3.Connection:
    from sable.shared.paths import sable_db_path

    conn = sqlite3.connect(str(sable_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply pending migrations to bring sable.db up to current version."""
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        current = row[0] if row else 0
    except sqlite3.OperationalError:
        current = 0  # schema_version table doesn't exist yet

    migrations_dir = Path(__file__).parent.parent / "db" / "migrations"
    for filename, target_version in _MIGRATIONS:
        if current < target_version:
            sql_path = migrations_dir / filename
            conn.executescript(sql_path.read_text())
            current = target_version
