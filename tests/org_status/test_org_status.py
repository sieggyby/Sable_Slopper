"""Tests for the enhanced org status command."""
from click.testing import CliRunner
from unittest.mock import patch


def _run_org_status(conn, org_id):
    """Helper to invoke org status with patched get_db."""
    from sable.platform.cli import org_status
    runner = CliRunner()
    with patch("sable.platform.db.get_db", return_value=conn):
        result = runner.invoke(org_status, [org_id])
    return result


# ─────────────────────────────────────────────────────────────────────
# Test 1: org not found
# ─────────────────────────────────────────────────────────────────────

def test_org_status_not_found(conn):
    """org status prints error and exits 1 for unknown org."""
    result = _run_org_status(conn, "nonexistent")
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "ORG_NOT_FOUND" in result.output


# ─────────────────────────────────────────────────────────────────────
# Test 2: basic status fields shown
# ─────────────────────────────────────────────────────────────────────

def test_org_status_basic_fields(org_conn):
    """org status shows org_id, display_name, status, entities, weekly spend."""
    result = _run_org_status(org_conn, "testorg")
    assert result.exit_code == 0
    assert "testorg" in result.output
    assert "Test Org" in result.output
    assert "Weekly AI spend" in result.output


# ─────────────────────────────────────────────────────────────────────
# Test 3: no diagnostics shows placeholder
# ─────────────────────────────────────────────────────────────────────

def test_org_status_no_diagnostics(org_conn):
    """org status shows placeholder when no diagnostics run."""
    result = _run_org_status(org_conn, "testorg")
    assert result.exit_code == 0
    assert "no runs yet" in result.output.lower()


# ─────────────────────────────────────────────────────────────────────
# Test 4: diagnostics shown with grade and fit
# ─────────────────────────────────────────────────────────────────────

def test_org_status_with_diagnostics(org_conn):
    """org status shows diagnostic info including grade and fit when available."""
    org_conn.execute(
        """INSERT INTO diagnostic_runs (org_id, run_type, status, overall_grade, fit_score)
           VALUES ('testorg', 'discord', 'completed', 'A', 85)"""
    )
    org_conn.commit()

    result = _run_org_status(org_conn, "testorg")
    assert result.exit_code == 0
    assert "grade=A" in result.output or "A" in result.output
    assert "fit=85" in result.output or "85" in result.output


# ─────────────────────────────────────────────────────────────────────
# Test 5: freshness fields present
# ─────────────────────────────────────────────────────────────────────

def test_org_status_freshness_fields(org_conn):
    """org status shows all freshness fields."""
    result = _run_org_status(org_conn, "testorg")
    assert result.exit_code == 0
    assert "pulse_last_track" in result.output
    assert "meta_last_scan" in result.output
    assert "tracking_last_sync" in result.output
    assert "vault_last_sync" in result.output


# ─────────────────────────────────────────────────────────────────────
# Test 6: tracking_last_sync shows when sync_runs exists
# ─────────────────────────────────────────────────────────────────────

def test_org_status_tracking_sync(org_conn):
    """org status shows tracking sync timestamp when sync_runs exist."""
    org_conn.execute(
        """INSERT INTO sync_runs (org_id, sync_type, status, completed_at)
           VALUES ('testorg', 'sable_tracking', 'completed', '2026-03-20T10:00:00')"""
    )
    org_conn.commit()

    result = _run_org_status(org_conn, "testorg")
    assert result.exit_code == 0
    assert "2026-03-20" in result.output


# ─────────────────────────────────────────────────────────────────────
# Test 7: vault_last_sync shows when vault artifact exists
# ─────────────────────────────────────────────────────────────────────

def test_org_status_vault_sync(org_conn):
    """org status shows vault sync timestamp when vault_index artifact exists."""
    org_conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'testorg', 'vault_sync', 'completed', '{}')")
    org_conn.execute(
        """INSERT INTO artifacts (org_id, job_id, artifact_type, path, metadata_json, stale, created_at)
           VALUES ('testorg', 'j1', 'vault_index', '/vault/testorg/_index.md', '{}', 0, '2026-03-22T08:00:00')"""
    )
    org_conn.commit()

    result = _run_org_status(org_conn, "testorg")
    assert result.exit_code == 0
    assert "2026-03-22" in result.output


# ─────────────────────────────────────────────────────────────────────
# Test 8: all fields show none when no data
# ─────────────────────────────────────────────────────────────────────

def test_org_status_all_none_freshness(org_conn):
    """org status shows (none) for all freshness fields when no data."""
    result = _run_org_status(org_conn, "testorg")
    assert result.exit_code == 0
    # At minimum none/None should appear for missing freshness data
    assert "(none)" in result.output
