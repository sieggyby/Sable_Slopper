"""Tests for sable.pulse.meta.cli — T2-3: CLI entry point wiring."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from sable.pulse.meta.cli import meta_group


def test_scan_dry_run_no_api_calls():
    """--dry-run returns cost estimate without making API calls."""
    runner = CliRunner()
    with patch("sable.pulse.meta.db.migrate"), \
         patch("sable.pulse.meta.watchlist.list_watchlist", return_value=[{"handle": "@alice"}]), \
         patch("sable.config.load_config", return_value={"pulse_meta": {"max_cost_per_run": 1.0}}):

        result = runner.invoke(meta_group, ["scan", "--org", "testorg", "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_scan_empty_watchlist():
    """Scan with empty watchlist prints warning and exits cleanly."""
    runner = CliRunner()
    with patch("sable.pulse.meta.db.migrate"), \
         patch("sable.pulse.meta.watchlist.list_watchlist", return_value=[]), \
         patch("sable.config.load_config", return_value={}):

        result = runner.invoke(meta_group, ["scan", "--org", "testorg"])

    assert result.exit_code == 0
    assert "No accounts in watchlist" in result.output


def test_status_shows_header():
    """Status command renders column headers."""
    runner = CliRunner()
    mock_rows = [{"org": "testorg", "last_scan_at": "2026-03-20 12:00:00", "scan_count": 5}]
    with patch("sable.pulse.meta.db.migrate"), \
         patch("sable.pulse.meta.db.get_scan_summary_all_orgs", return_value=mock_rows):
        result = runner.invoke(meta_group, ["status"])

    assert result.exit_code == 0
    assert "testorg" in result.output


def test_status_no_scans():
    """Status with no scan history prints dim message."""
    runner = CliRunner()
    with patch("sable.pulse.meta.db.migrate"), \
         patch("sable.pulse.meta.db.get_scan_summary_all_orgs", return_value=[]):
        result = runner.invoke(meta_group, ["status"])

    assert result.exit_code == 0
    assert "No scans recorded" in result.output


def test_meta_group_no_args_shows_help():
    """meta group with no subcommand and no --org shows help."""
    runner = CliRunner()
    result = runner.invoke(meta_group, [])
    assert result.exit_code == 0
    assert "Content shape intelligence" in result.output or "Usage" in result.output
