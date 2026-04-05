"""Tests for register_content_artifact helper."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch, MagicMock

import pytest


class _NoCloseConn:
    """Wrapper that suppresses .close() so test fixtures survive."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.close_called = False

    def close(self):
        self.close_called = True

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _make_db():
    """Create in-memory sable.db with artifacts table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE artifacts (
            artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            job_id TEXT,
            artifact_type TEXT NOT NULL,
            path TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            stale INTEGER NOT NULL DEFAULT 0,
            degraded INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def test_register_basic():
    """Registers an artifact with correct columns."""
    raw_conn = _make_db()
    wrapper = _NoCloseConn(raw_conn)
    with patch("sable.platform.db.get_db", return_value=wrapper):
        from sable.platform.artifacts import register_content_artifact
        register_content_artifact(
            org_id="psy",
            artifact_type="content_meme",
            path="/tmp/meme.png",
            metadata={"handle": "@test", "template": "drake"},
        )

    row = raw_conn.execute("SELECT * FROM artifacts").fetchone()
    assert row["org_id"] == "psy"
    assert row["artifact_type"] == "content_meme"
    assert row["path"] == "/tmp/meme.png"
    meta = json.loads(row["metadata_json"])
    assert meta["handle"] == "@test"
    assert meta["template"] == "drake"
    assert row["stale"] == 0
    assert row["degraded"] == 0
    assert wrapper.close_called


def test_register_none_path():
    """Path can be None (stored as NULL)."""
    raw_conn = _make_db()
    wrapper = _NoCloseConn(raw_conn)
    with patch("sable.platform.db.get_db", return_value=wrapper):
        from sable.platform.artifacts import register_content_artifact
        register_content_artifact(
            org_id="psy",
            artifact_type="content_text",
            path=None,
        )

    row = raw_conn.execute("SELECT * FROM artifacts").fetchone()
    assert row["path"] is None
    assert json.loads(row["metadata_json"]) == {}


def test_register_none_metadata():
    """Metadata defaults to empty dict when None."""
    raw_conn = _make_db()
    wrapper = _NoCloseConn(raw_conn)
    with patch("sable.platform.db.get_db", return_value=wrapper):
        from sable.platform.artifacts import register_content_artifact
        register_content_artifact(
            org_id="psy",
            artifact_type="content_clip",
            path="/tmp/clip.mp4",
            metadata=None,
        )

    row = raw_conn.execute("SELECT * FROM artifacts").fetchone()
    assert json.loads(row["metadata_json"]) == {}


def test_register_non_fatal_on_db_error():
    """DB error is swallowed with warning, does not crash."""
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = sqlite3.OperationalError("table not found")
    with patch("sable.platform.db.get_db", return_value=mock_conn):
        from sable.platform.artifacts import register_content_artifact
        # Should not raise
        register_content_artifact(
            org_id="psy",
            artifact_type="content_meme",
            path="/tmp/meme.png",
        )
    mock_conn.close.assert_called_once()
