"""Shared FastAPI dependencies — DB connections and path resolution."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from sable.shared.paths import pulse_db_path, meta_db_path, vault_dir


def get_pulse_db() -> sqlite3.Connection:
    """Return a fresh pulse.db connection (one per call, thread-safe)."""
    conn = sqlite3.connect(str(pulse_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_meta_db() -> sqlite3.Connection:
    """Return a fresh meta.db connection (one per call, thread-safe)."""
    conn = sqlite3.connect(str(meta_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_vault_path(org: str) -> Path:
    return vault_dir(org)
