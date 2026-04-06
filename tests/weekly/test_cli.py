"""Tests for sable.weekly.cli."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from sable.weekly.cli import weekly_group
from sable.weekly.runner import StepResult


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setenv("SABLE_WORKSPACE", str(tmp_path / "workspace"))


def _make_account(handle: str, org: str):
    acc = MagicMock()
    acc.handle = handle
    acc.org = org
    return acc


class TestWeeklyRunCLI:
    def test_requires_org_or_all(self):
        runner = CliRunner()
        result = runner.invoke(weekly_group, ["run"])
        assert result.exit_code != 0
        assert "Provide --org ORG or --all" in result.output

    def test_org_and_all_mutually_exclusive(self):
        runner = CliRunner()
        result = runner.invoke(weekly_group, ["run", "--org", "x", "--all"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    @patch("sable.weekly.runner.WeeklyRunner.run")
    def test_run_success(self, mock_run):
        mock_run.return_value = [
            StepResult(name="pulse_track", status="ok", duration_s=10, cost_usd=0.01),
            StepResult(name="meta_scan", status="ok", duration_s=30, cost_usd=0.15),
            StepResult(name="advise", status="ok", duration_s=20, cost_usd=0.20),
            StepResult(name="calendar", status="ok", duration_s=15, cost_usd=0.05),
            StepResult(name="vault_sync", status="ok", duration_s=5, cost_usd=0.0),
        ]

        runner = CliRunner()
        result = runner.invoke(weekly_group, ["run", "--org", "my_org"])
        assert result.exit_code == 0
        assert "5/5 steps succeeded" in result.output

    @patch("sable.weekly.runner.WeeklyRunner.run")
    def test_run_with_failure_exits_nonzero(self, mock_run):
        mock_run.return_value = [
            StepResult(name="pulse_track", status="ok", duration_s=10, cost_usd=0.01),
            StepResult(name="advise", status="error", duration_s=2, error="boom"),
        ]

        runner = CliRunner()
        result = runner.invoke(weekly_group, ["run", "--org", "my_org"])
        assert result.exit_code == 1

    @patch("sable.weekly.runner.discover_orgs", return_value=["org_a", "org_b"])
    @patch("sable.weekly.runner.WeeklyRunner.run")
    def test_all_iterates_orgs(self, mock_run, mock_discover):
        mock_run.return_value = [
            StepResult(name="pulse_track", status="ok", duration_s=5, cost_usd=0.01),
        ]

        runner = CliRunner()
        result = runner.invoke(weekly_group, ["run", "--all"])
        assert result.exit_code == 0
        assert mock_run.call_count == 2
        assert "org_a" in result.output
        assert "org_b" in result.output

    @patch("sable.weekly.runner.discover_orgs", return_value=["org_a"])
    @patch("sable.roster.manager.list_accounts")
    def test_dry_run_no_execution(self, mock_list, mock_discover):
        mock_list.return_value = [_make_account("@alice", "org_a")]

        runner = CliRunner()
        result = runner.invoke(weekly_group, ["run", "--all", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "org_a" in result.output
        assert "@alice" in result.output

    @patch("sable.weekly.runner.discover_orgs", return_value=["org_a"])
    @patch("sable.weekly.runner.estimate_org_cost", return_value=1.50)
    def test_cost_estimate(self, mock_est, mock_discover):
        runner = CliRunner()
        result = runner.invoke(weekly_group, ["run", "--all", "--cost-estimate"])
        assert result.exit_code == 0
        assert "$1.50" in result.output
        assert "Total" in result.output

    @patch("sable.weekly.runner.discover_orgs", return_value=[])
    def test_all_no_orgs(self, mock_discover):
        runner = CliRunner()
        result = runner.invoke(weekly_group, ["run", "--all"])
        assert result.exit_code == 0
        assert "No orgs" in result.output


class TestCronInstallCLI:
    def test_install_writes_plist(self, tmp_path, monkeypatch):
        launch_agents = tmp_path / "Library" / "LaunchAgents"
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        runner = CliRunner()
        result = runner.invoke(weekly_group, ["cron", "install"])
        assert result.exit_code == 0
        assert "Plist written to" in result.output
        assert "launchctl load" in result.output

        plist = launch_agents / "com.sable.weekly.plist"
        assert plist.exists()

        content = plist.read_text()
        assert "<string>com.sable.weekly</string>" in content
        assert "<key>Weekday</key>" in content
        assert "<integer>1</integer>" in content  # Monday
        assert "<key>Hour</key>" in content
        assert "<integer>6</integer>" in content
        assert "--json-log" in content
        assert "--all" in content
        assert "<false/>" in content  # RunAtLoad=false

    def test_install_creates_logs_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        runner = CliRunner()
        result = runner.invoke(weekly_group, ["cron", "install"])
        assert result.exit_code == 0

        logs_dir = tmp_path / ".sable" / "logs"
        assert logs_dir.exists()
