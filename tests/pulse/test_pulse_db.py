"""AQ-29: Tests for pulse.db — migrate, insert_post, get_posts_for_account."""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest


def _make_pulse_db(tmp_path):
    """Create a real pulse.db via migrate()."""
    db_path = tmp_path / "pulse.db"
    with patch("sable.pulse.db.pulse_db_path", return_value=db_path):
        from sable.pulse.db import migrate
        migrate()
    return db_path


def test_migrate_creates_schema(tmp_path):
    """Fresh migrate → tables and version created."""
    db_path = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Tables exist
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "posts" in tables
    assert "snapshots" in tables
    assert "account_stats" in tables
    assert "schema_version" in tables

    # Version set
    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version >= 1

    conn.close()


def test_migrate_wal_mode(tmp_path):
    """get_conn enables WAL mode."""
    db_path = tmp_path / "pulse.db"
    with patch("sable.pulse.db.pulse_db_path", return_value=db_path):
        from sable.pulse.db import get_conn
        conn = get_conn()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()


def test_insert_post_deduplication(tmp_path):
    """insert_post returns True first time, False on duplicate (AR5-24)."""
    db_path = _make_pulse_db(tmp_path)
    with patch("sable.pulse.db.pulse_db_path", return_value=db_path):
        from sable.pulse.db import insert_post
        assert insert_post("p1", "@test", text="hello") is True
        assert insert_post("p1", "@test", text="hello") is False


def test_insert_post_handle_normalization(tmp_path):
    """Bare handle gets @-prefixed."""
    db_path = _make_pulse_db(tmp_path)
    with patch("sable.pulse.db.pulse_db_path", return_value=db_path):
        from sable.pulse.db import insert_post, get_posts_for_account
        insert_post("p2", "testuser", text="gm")
        posts = get_posts_for_account("@testuser")
        assert len(posts) == 1
        assert posts[0]["account_handle"] == "@testuser"


def test_insert_post_thread_columns(tmp_path):
    """Thread columns round-trip correctly."""
    db_path = _make_pulse_db(tmp_path)
    with patch("sable.pulse.db.pulse_db_path", return_value=db_path):
        from sable.pulse.db import insert_post, get_posts_for_account
        insert_post("p3", "@thread_user", is_thread=True, thread_length=5)
        posts = get_posts_for_account("@thread_user")
        assert len(posts) == 1
        assert posts[0]["is_thread"] == 1
        assert posts[0]["thread_length"] == 5


def test_get_posts_for_account_empty(tmp_path):
    """No posts → empty list."""
    db_path = _make_pulse_db(tmp_path)
    with patch("sable.pulse.db.pulse_db_path", return_value=db_path):
        from sable.pulse.db import get_posts_for_account
        assert get_posts_for_account("@nobody") == []
