"""Tests for sync_runs freshness writes in pulse track and meta scan."""
import sqlite3
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from sable.platform.db import ensure_schema


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def sable_conn():
    """In-memory sable.db with schema."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_schema(c)
    c.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    c.commit()
    yield c
    c.close()


class _NoCloseConn:
    """Wrapper that suppresses .close() so test fixtures survive production code."""

    def __init__(self, real):
        self._real = real
        self.row_factory = real.row_factory

    def execute(self, *a, **kw):
        return self._real.execute(*a, **kw)

    def commit(self):
        return self._real.commit()

    def close(self):
        pass  # suppress

    def __getattr__(self, name):
        return getattr(self._real, name)


def _mock_account(handle="@alice", org="testorg"):
    from sable.roster.models import Account, Persona, ContentSettings
    return Account(handle=handle, org=org, display_name="Alice",
                   persona=Persona(), content=ContentSettings())


# ─────────────────────────────────────────────────────────────────────
# Test 1: pulse track writes sync_runs row
# ─────────────────────────────────────────────────────────────────────

def test_pulse_track_writes_sync_run(sable_conn):
    """pulse track records a sync_runs row with sync_type='pulse_track'."""
    from sable.pulse.cli import pulse_group
    from sable.roster.models import Roster

    mock_roster = Roster(accounts=[_mock_account()])
    fake_tweets = [{"id": "1", "text": "hi"}] * 5
    wrapper = _NoCloseConn(sable_conn)

    runner = CliRunner()
    with patch("sable.pulse.tracker.snapshot_account", return_value=fake_tweets), \
         patch("sable.pulse.db.migrate"), \
         patch("sable.roster.manager.load_roster", return_value=mock_roster), \
         patch("sable.platform.db.get_db", return_value=wrapper):
        result = runner.invoke(pulse_group, ["track", "--account", "alice"])

    assert result.exit_code == 0, result.output

    row = sable_conn.execute(
        "SELECT * FROM sync_runs WHERE sync_type='pulse_track'"
    ).fetchone()
    assert row is not None
    assert row["org_id"] == "testorg"
    assert row["status"] == "completed"
    assert row["records_synced"] == 5


# ─────────────────────────────────────────────────────────────────────
# Test 2: pulse track skips sync when no org
# ─────────────────────────────────────────────────────────────────────

def test_pulse_track_no_org_skips_sync_run(sable_conn):
    """pulse track skips sync_runs write when handle has no org."""
    from sable.pulse.cli import pulse_group
    from sable.roster.models import Roster

    mock_roster = Roster(accounts=[_mock_account(org="")])
    fake_tweets = [{"id": "1", "text": "hi"}]

    runner = CliRunner()
    with patch("sable.pulse.tracker.snapshot_account", return_value=fake_tweets), \
         patch("sable.pulse.db.migrate"), \
         patch("sable.roster.manager.load_roster", return_value=mock_roster):
        result = runner.invoke(pulse_group, ["track", "--account", "alice"])

    assert result.exit_code == 0, result.output

    row = sable_conn.execute(
        "SELECT * FROM sync_runs WHERE sync_type='pulse_track'"
    ).fetchone()
    assert row is None


# ─────────────────────────────────────────────────────────────────────
# Test 3: pulse track skips sync when not in roster
# ─────────────────────────────────────────────────────────────────────

def test_pulse_track_not_in_roster_skips_sync_run(sable_conn):
    """pulse track skips sync_runs write when handle not in roster."""
    from sable.pulse.cli import pulse_group
    from sable.roster.models import Roster

    mock_roster = Roster(accounts=[])  # empty roster
    fake_tweets = [{"id": "1", "text": "hi"}]

    runner = CliRunner()
    with patch("sable.pulse.tracker.snapshot_account", return_value=fake_tweets), \
         patch("sable.pulse.db.migrate"), \
         patch("sable.roster.manager.load_roster", return_value=mock_roster):
        result = runner.invoke(pulse_group, ["track", "--account", "alice"])

    assert result.exit_code == 0, result.output

    row = sable_conn.execute(
        "SELECT * FROM sync_runs WHERE sync_type='pulse_track'"
    ).fetchone()
    assert row is None


# ─────────────────────────────────────────────────────────────────────
# Test 4: pulse track sync failure is non-fatal
# ─────────────────────────────────────────────────────────────────────

def test_pulse_track_sync_failure_nonfatal():
    """sync_runs write failure does not crash pulse track."""
    from sable.pulse.cli import pulse_group
    from sable.roster.models import Roster

    mock_roster = Roster(accounts=[_mock_account()])
    fake_tweets = [{"id": "1", "text": "hi"}]

    def failing_get_db():
        raise sqlite3.OperationalError("sable.db locked")

    runner = CliRunner()
    with patch("sable.pulse.tracker.snapshot_account", return_value=fake_tweets), \
         patch("sable.pulse.db.migrate"), \
         patch("sable.roster.manager.load_roster", return_value=mock_roster), \
         patch("sable.platform.db.get_db", side_effect=failing_get_db):
        result = runner.invoke(pulse_group, ["track", "--account", "alice"])

    assert result.exit_code == 0, result.output
    assert "Tracked" in result.output


# ─────────────────────────────────────────────────────────────────────
# Test 5: meta scan writes sync_runs row
# ─────────────────────────────────────────────────────────────────────

def test_meta_scan_writes_sync_run(sable_conn):
    """pulse meta scan records a sync_runs row with sync_type='pulse_meta_scan'."""
    from sable.pulse.meta.cli import meta_group

    scan_result = {
        "tweets_collected": 100,
        "tweets_new": 42,
        "estimated_cost": 0.05,
        "failed_authors": [],
    }
    mock_scanner = MagicMock()
    mock_scanner.return_value.run.return_value = scan_result
    wrapper = _NoCloseConn(sable_conn)

    # Mock meta_db functions that meta_scan calls
    mock_meta_db = MagicMock()
    mock_meta_db.create_scan_run.return_value = "scan_001"
    mock_meta_db.get_scan_runs.return_value = [1, 2, 3]

    runner = CliRunner()
    with patch("sable.pulse.meta.db.migrate", mock_meta_db.migrate), \
         patch("sable.pulse.meta.db.create_scan_run", mock_meta_db.create_scan_run), \
         patch("sable.pulse.meta.db.get_scan_runs", mock_meta_db.get_scan_runs), \
         patch("sable.pulse.meta.db.complete_scan_run", mock_meta_db.complete_scan_run), \
         patch("sable.pulse.meta.watchlist.list_watchlist", return_value=["@alice", "@bob"]), \
         patch("sable.pulse.meta.scanner.Scanner", mock_scanner), \
         patch("sable.platform.db.get_db", return_value=wrapper), \
         patch("sable.config.load_config", return_value={"pulse_meta": {"max_cost_per_run": 1.0}}):
        result = runner.invoke(meta_group, ["scan", "--org", "testorg"])

    assert result.exit_code == 0, result.output

    row = sable_conn.execute(
        "SELECT * FROM sync_runs WHERE sync_type='pulse_meta_scan'"
    ).fetchone()
    assert row is not None
    assert row["org_id"] == "testorg"
    assert row["status"] == "completed"
    assert row["records_synced"] == 42


# ─────────────────────────────────────────────────────────────────────
# Test 6: meta scan sync failure is non-fatal
# ─────────────────────────────────────────────────────────────────────

def test_meta_scan_sync_failure_nonfatal():
    """sync_runs write failure does not crash pulse meta scan."""
    from sable.pulse.meta.cli import meta_group

    scan_result = {
        "tweets_collected": 10,
        "tweets_new": 5,
        "estimated_cost": 0.01,
        "failed_authors": [],
    }
    mock_scanner = MagicMock()
    mock_scanner.return_value.run.return_value = scan_result

    mock_meta_db = MagicMock()
    mock_meta_db.create_scan_run.return_value = "scan_001"
    mock_meta_db.get_scan_runs.return_value = [1, 2, 3]

    def failing_get_db():
        raise sqlite3.OperationalError("sable.db locked")

    runner = CliRunner()
    with patch("sable.pulse.meta.db.migrate", mock_meta_db.migrate), \
         patch("sable.pulse.meta.db.create_scan_run", mock_meta_db.create_scan_run), \
         patch("sable.pulse.meta.db.get_scan_runs", mock_meta_db.get_scan_runs), \
         patch("sable.pulse.meta.db.complete_scan_run", mock_meta_db.complete_scan_run), \
         patch("sable.pulse.meta.watchlist.list_watchlist", return_value=["@alice"]), \
         patch("sable.pulse.meta.scanner.Scanner", mock_scanner), \
         patch("sable.platform.db.get_db", side_effect=failing_get_db), \
         patch("sable.config.load_config", return_value={"pulse_meta": {"max_cost_per_run": 1.0}}):
        result = runner.invoke(meta_group, ["scan", "--org", "testorg"])

    assert result.exit_code == 0, result.output
    assert "Scan complete" in result.output
