"""Tests for sable.platform.cli — T3-5: CLI entry point wiring."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from sable.platform.cli import db_group, org_group


# ---------------------------------------------------------------------------
# org commands
# ---------------------------------------------------------------------------

def _mock_conn_with_rows(rows, columns=None):
    """Create a mock connection that returns given rows from execute().fetchall/fetchone."""
    conn = MagicMock(spec=sqlite3.Connection)
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    cursor.fetchone.return_value = rows[0] if rows else None
    conn.execute.return_value = cursor
    return conn


def test_org_list_no_orgs():
    """org list with no rows prints '(no orgs)'."""
    runner = CliRunner()
    mock_conn = _mock_conn_with_rows([])

    with patch("sable.platform.db.get_db", return_value=mock_conn):
        result = runner.invoke(org_group, ["list"])

    assert result.exit_code == 0
    assert "(no orgs)" in result.output


def test_org_list_shows_orgs():
    """org list renders org rows."""
    runner = CliRunner()
    row = {"org_id": "testorg", "display_name": "Test Org", "status": "active"}
    mock_conn = _mock_conn_with_rows([row])

    with patch("sable.platform.db.get_db", return_value=mock_conn):
        result = runner.invoke(org_group, ["list"])

    assert result.exit_code == 0
    assert "testorg" in result.output


# ---------------------------------------------------------------------------
# db commands
# ---------------------------------------------------------------------------

def test_db_status_shows_path_and_version():
    """db status renders path and version."""
    runner = CliRunner()
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {"version": 6}

    with patch("sable.platform.db.get_db", return_value=mock_conn), \
         patch("sable.shared.paths.sable_db_path", return_value="/fake/sable.db"):
        result = runner.invoke(db_group, ["status"])

    assert result.exit_code == 0
    assert "Version" in result.output
