"""Shared SQLite connection factory and migration runner for sable.db."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def get_db() -> sqlite3.Connection:
    from sable.shared.paths import sable_db_path

    conn = sqlite3.connect(str(sable_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply pending migrations to bring sable.db up to current version.

    Scans the local migrations directory dynamically so new migration files
    are picked up without code changes.
    """
    import re

    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        current = row[0] if row else 0
    except sqlite3.OperationalError:
        current = 0

    migrations_dir = Path(__file__).parent.parent / "db" / "migrations"
    for mf in sorted(migrations_dir.glob("0[0-9][0-9]_*.sql")):
        m = re.match(r"^(\d+)_", mf.name)
        if not m:
            continue
        target_version = int(m.group(1))
        if current >= target_version:
            continue
        sql = mf.read_text()
        stmts = [s.strip() for s in sql.split(";") if s.strip()]
        with conn:
            for stmt in stmts:
                conn.execute(stmt)
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (target_version,)
            )
        current = target_version
