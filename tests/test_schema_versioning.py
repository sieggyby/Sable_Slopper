"""Tests for SS-13: schema versioning for pulse.db and meta.db."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _in_memory_pulse(tmp_path: Path):
    """Patch pulse_db_path so pulse.db lives in tmp_path."""
    return patch("sable.pulse.db.pulse_db_path", return_value=tmp_path / "pulse.db")


def _in_memory_meta(tmp_path: Path):
    """Patch meta_db_path so meta.db lives in tmp_path."""
    p = tmp_path / "pulse"
    p.mkdir(exist_ok=True)
    return patch("sable.pulse.meta.db.meta_db_path", return_value=p / "meta.db")


# ---------------------------------------------------------------------------
# pulse.db tests
# ---------------------------------------------------------------------------

class TestPulseSchemaVersioning:
    def test_fresh_db_gets_current_version(self, tmp_path):
        from sable.pulse.db import SCHEMA_VERSION
        with _in_memory_pulse(tmp_path):
            from sable.pulse.db import migrate, get_conn
            migrate()
            conn = get_conn()
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            assert row["version"] == SCHEMA_VERSION
            conn.close()

    def test_already_at_version_is_noop(self, tmp_path, caplog):
        with _in_memory_pulse(tmp_path):
            from sable.pulse.db import migrate, get_conn, SCHEMA_VERSION
            migrate()  # first run
            with caplog.at_level(logging.INFO, logger="sable.pulse.db"):
                migrate()  # second run — should be a no-op
            # No "migrated" log line on second run
            migration_msgs = [r for r in caplog.records if "migrated" in r.message.lower() or "→" in r.message]
            assert len(migration_msgs) == 0
            conn = get_conn()
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            assert row["version"] == SCHEMA_VERSION
            conn.close()

    def test_version_upgraded_from_old(self, tmp_path, caplog):
        """Simulate a DB stuck at version 1 and verify migrate() bumps it."""
        with _in_memory_pulse(tmp_path):
            from sable.pulse.db import migrate, get_conn, SCHEMA_VERSION, _SCHEMA
            # Bootstrap the DB at version 1
            conn = get_conn()
            conn.executescript(_SCHEMA)
            conn.execute("INSERT INTO schema_version VALUES (1)")
            conn.commit()
            conn.close()
            # Now migrate — should bump to current
            with caplog.at_level(logging.INFO, logger="sable.pulse.db"):
                migrate()
            conn = get_conn()
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            assert row["version"] == SCHEMA_VERSION
            conn.close()
            if SCHEMA_VERSION > 1:
                assert any("→" in r.message for r in caplog.records)

    def test_future_version_skipped(self, tmp_path, caplog):
        """If DB version is ahead of code, migration should warn and skip."""
        with _in_memory_pulse(tmp_path):
            from sable.pulse.db import migrate, get_conn, SCHEMA_VERSION, _SCHEMA
            conn = get_conn()
            conn.executescript(_SCHEMA)
            conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION + 99,))
            conn.commit()
            conn.close()
            with caplog.at_level(logging.WARNING, logger="sable.pulse.db"):
                migrate()
            conn = get_conn()
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            assert row["version"] == SCHEMA_VERSION + 99  # unchanged
            conn.close()
            assert any("ahead" in r.message.lower() for r in caplog.records)

    def test_incremental_migration_executes_stmts(self, tmp_path):
        """Verify that SQL statements in _MIGRATIONS are actually executed."""
        with _in_memory_pulse(tmp_path):
            from sable.pulse import db as pulse_db
            # Bootstrap at version 2 (current), then add a fake v3 migration
            pulse_db.migrate()
            old_version = pulse_db.SCHEMA_VERSION
            # Patch in a v3 migration that adds a column
            try:
                pulse_db.SCHEMA_VERSION = old_version + 1
                pulse_db._MIGRATIONS[old_version + 1] = [
                    "ALTER TABLE posts ADD COLUMN test_col TEXT DEFAULT 'hello'"
                ]
                pulse_db.migrate()
                conn = pulse_db.get_conn()
                row = conn.execute("SELECT version FROM schema_version").fetchone()
                assert row["version"] == old_version + 1
                # Verify column exists
                row = conn.execute("SELECT test_col FROM posts LIMIT 1").fetchone()
                conn.close()
            finally:
                pulse_db.SCHEMA_VERSION = old_version
                pulse_db._MIGRATIONS.pop(old_version + 1, None)


# ---------------------------------------------------------------------------
# meta.db tests
# ---------------------------------------------------------------------------

class TestMetaSchemaVersioning:
    def test_fresh_db_gets_current_version(self, tmp_path):
        from sable.pulse.meta.db import SCHEMA_VERSION
        with _in_memory_meta(tmp_path):
            from sable.pulse.meta.db import migrate, get_conn
            migrate()
            conn = get_conn()
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            assert row["version"] == SCHEMA_VERSION
            conn.close()

    def test_already_at_version_is_noop(self, tmp_path, caplog):
        with _in_memory_meta(tmp_path):
            from sable.pulse.meta.db import migrate, get_conn, SCHEMA_VERSION
            migrate()
            with caplog.at_level(logging.INFO, logger="sable.pulse.meta.db"):
                migrate()
            migration_msgs = [r for r in caplog.records if "migrated" in r.message.lower() or "→" in r.message]
            assert len(migration_msgs) == 0
            conn = get_conn()
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            assert row["version"] == SCHEMA_VERSION
            conn.close()

    def test_version_upgraded_from_old(self, tmp_path, caplog):
        with _in_memory_meta(tmp_path):
            from sable.pulse.meta.db import migrate, get_conn, SCHEMA_VERSION, _SCHEMA
            conn = get_conn()
            conn.executescript(_SCHEMA)
            conn.execute("INSERT INTO schema_version VALUES (1)")
            conn.commit()
            conn.close()
            with caplog.at_level(logging.INFO, logger="sable.pulse.meta.db"):
                migrate()
            conn = get_conn()
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            assert row["version"] == SCHEMA_VERSION
            conn.close()
            assert any("→" in r.message for r in caplog.records)

    def test_future_version_skipped(self, tmp_path, caplog):
        with _in_memory_meta(tmp_path):
            from sable.pulse.meta.db import migrate, get_conn, SCHEMA_VERSION, _SCHEMA
            conn = get_conn()
            conn.executescript(_SCHEMA)
            conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION + 99,))
            conn.commit()
            conn.close()
            with caplog.at_level(logging.WARNING, logger="sable.pulse.meta.db"):
                migrate()
            conn = get_conn()
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            assert row["version"] == SCHEMA_VERSION + 99
            conn.close()
            assert any("ahead" in r.message.lower() for r in caplog.records)

    def test_incremental_migration_executes_stmts(self, tmp_path):
        with _in_memory_meta(tmp_path):
            from sable.pulse.meta import db as meta_db
            meta_db.migrate()
            old_version = meta_db.SCHEMA_VERSION
            try:
                meta_db.SCHEMA_VERSION = old_version + 1
                meta_db._MIGRATIONS[old_version + 1] = [
                    "ALTER TABLE scanned_tweets ADD COLUMN test_col TEXT DEFAULT 'hello'"
                ]
                meta_db.migrate()
                conn = meta_db.get_conn()
                row = conn.execute("SELECT version FROM schema_version").fetchone()
                assert row["version"] == old_version + 1
                row = conn.execute("SELECT test_col FROM scanned_tweets LIMIT 1").fetchone()
                conn.close()
            finally:
                meta_db.SCHEMA_VERSION = old_version
                meta_db._MIGRATIONS.pop(old_version + 1, None)
