"""CLI smoke tests for sable lexicon commands."""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

from click.testing import CliRunner

from sable.pulse.meta.db import _SCHEMA
from sable.lexicon.cli import lexicon_group


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _invoke(conn, args):
    runner = CliRunner()
    with patch("sable.pulse.meta.db.get_conn", return_value=conn), \
         patch("sable.pulse.meta.db.migrate"):
        return runner.invoke(lexicon_group, args)


def test_scan_empty_org():
    """Scan with no data shows threshold message."""
    conn = _make_conn()
    result = _invoke(conn, ["scan", "--org", "empty"])
    assert result.exit_code == 0
    assert "Insufficient data" in result.output


def test_list_empty():
    """List with no terms shows help message."""
    conn = _make_conn()
    result = _invoke(conn, ["list", "--org", "test"])
    assert result.exit_code == 0
    assert "No lexicon terms" in result.output


def test_add_and_list():
    """Add a term then list it."""
    conn = _make_conn()
    result = _invoke(conn, ["add", "--org", "test", "--term", "zkrollup", "--gloss", "ZK tech"])
    assert result.exit_code == 0
    assert "Added" in result.output

    result = _invoke(conn, ["list", "--org", "test"])
    assert result.exit_code == 0
    assert "zkrollup" in result.output


def test_remove_existing():
    """Remove an existing term."""
    conn = _make_conn()
    # Add first
    _invoke(conn, ["add", "--org", "test", "--term", "foo"])
    result = _invoke(conn, ["remove", "foo", "--org", "test"])
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_remove_nonexistent():
    """Remove nonexistent term shows warning."""
    conn = _make_conn()
    result = _invoke(conn, ["remove", "missing", "--org", "test"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_dry_run():
    """Dry run shows corpus stats."""
    conn = _make_conn()
    result = _invoke(conn, ["scan", "--org", "test", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "Tweets:" in result.output
    assert "Authors:" in result.output
