"""Tests for sable.weekly.runner."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sable.weekly.runner import (
    WeeklyRunner, StepResult, format_summary, discover_orgs, estimate_org_cost,
)


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setenv("SABLE_WORKSPACE", str(tmp_path / "workspace"))


def _make_account(handle: str, org: str):
    acc = MagicMock()
    acc.handle = handle
    acc.org = org
    return acc


class TestWeeklyRunner:
    """Test WeeklyRunner orchestration."""

    @patch("sable.weekly.runner.WeeklyRunner._step_vault_sync", return_value=0.0)
    @patch("sable.weekly.runner.WeeklyRunner._step_calendar", return_value=0.05)
    @patch("sable.weekly.runner.WeeklyRunner._step_advise", return_value=0.20)
    @patch("sable.weekly.runner.WeeklyRunner._step_meta_scan", return_value=0.15)
    @patch("sable.weekly.runner.WeeklyRunner._step_pulse_track", return_value=0.01)
    def test_run_all_steps_succeed(self, mock_pt, mock_ms, mock_adv, mock_cal, mock_vs):
        runner = WeeklyRunner("test_org")
        results = runner.run()

        assert len(results) == 5
        assert all(r.status == "ok" for r in results)
        mock_pt.assert_called_once()
        mock_ms.assert_called_once()
        mock_adv.assert_called_once()
        mock_cal.assert_called_once()
        mock_vs.assert_called_once()

    @patch("sable.weekly.runner.WeeklyRunner._step_vault_sync", return_value=0.0)
    @patch("sable.weekly.runner.WeeklyRunner._step_calendar", return_value=0.05)
    @patch("sable.weekly.runner.WeeklyRunner._step_advise", side_effect=RuntimeError("Claude down"))
    @patch("sable.weekly.runner.WeeklyRunner._step_meta_scan", return_value=0.15)
    @patch("sable.weekly.runner.WeeklyRunner._step_pulse_track", return_value=0.01)
    def test_partial_failure_continues(self, mock_pt, mock_ms, mock_adv, mock_cal, mock_vs):
        runner = WeeklyRunner("test_org")
        results = runner.run()

        assert len(results) == 5
        ok = [r for r in results if r.status == "ok"]
        errors = [r for r in results if r.status == "error"]
        assert len(ok) == 4
        assert len(errors) == 1
        assert errors[0].name == "advise"
        assert "Claude down" in errors[0].error
        # Steps after the failure still ran
        mock_cal.assert_called_once()
        mock_vs.assert_called_once()

    @patch("sable.weekly.runner.WeeklyRunner._step_vault_sync", return_value=0.0)
    @patch("sable.weekly.runner.WeeklyRunner._step_calendar", return_value=0.0)
    @patch("sable.weekly.runner.WeeklyRunner._step_advise", return_value=0.0)
    @patch("sable.weekly.runner.WeeklyRunner._step_meta_scan", return_value=0.0)
    @patch("sable.weekly.runner.WeeklyRunner._step_pulse_track", return_value=0.0)
    def test_step_order(self, mock_pt, mock_ms, mock_adv, mock_cal, mock_vs):
        runner = WeeklyRunner("test_org")
        results = runner.run()

        names = [r.name for r in results]
        assert names == ["pulse_track", "meta_scan", "advise", "calendar", "vault_sync"]

    def test_pulse_track_calls_snapshot(self):
        with (
            patch.object(WeeklyRunner, "_get_spend_before", return_value=0.0),
            patch.object(WeeklyRunner, "_get_accounts") as mock_accounts,
            patch("sable.pulse.tracker.snapshot_account") as mock_snap,
        ):
            mock_accounts.return_value = [
                _make_account("@alice", "test_org"),
                _make_account("@bob", "test_org"),
            ]
            runner = WeeklyRunner("test_org")
            runner._step_pulse_track()

            assert mock_snap.call_count == 2
            mock_snap.assert_any_call("@alice")
            mock_snap.assert_any_call("@bob")

    def test_pulse_track_no_accounts(self):
        with (
            patch.object(WeeklyRunner, "_get_spend_before", return_value=0.0),
            patch.object(WeeklyRunner, "_get_accounts", return_value=[]),
        ):
            runner = WeeklyRunner("test_org")
            cost = runner._step_pulse_track()
            assert cost == 0.0

    def test_advise_calls_generate(self):
        with (
            patch.object(WeeklyRunner, "_get_spend_before", return_value=0.0),
            patch.object(WeeklyRunner, "_get_accounts") as mock_accounts,
            patch("sable.advise.generate.generate_advise") as mock_gen,
        ):
            mock_accounts.return_value = [_make_account("@alice", "test_org")]
            runner = WeeklyRunner("test_org")
            runner._step_advise()

            mock_gen.assert_called_once_with("@alice", org="test_org")

    def test_vault_sync_calls_platform(self):
        with (
            patch.object(WeeklyRunner, "_get_spend_before", return_value=0.0),
            patch("sable.vault.platform_sync.platform_vault_sync") as mock_sync,
        ):
            runner = WeeklyRunner("test_org")
            runner._step_vault_sync()

            mock_sync.assert_called_once_with("test_org")


class TestFormatSummary:
    def test_all_ok(self):
        results = [
            StepResult(name="pulse_track", status="ok", duration_s=10, cost_usd=0.01),
            StepResult(name="meta_scan", status="ok", duration_s=30, cost_usd=0.15),
            StepResult(name="advise", status="ok", duration_s=20, cost_usd=0.20),
            StepResult(name="calendar", status="ok", duration_s=15, cost_usd=0.05),
            StepResult(name="vault_sync", status="ok", duration_s=5, cost_usd=0.0),
        ]
        summary = format_summary("test_org", results)
        assert "5/5 steps succeeded" in summary
        assert "$0.41" in summary
        assert "1m 20s" in summary

    def test_with_failure(self):
        results = [
            StepResult(name="pulse_track", status="ok", duration_s=10, cost_usd=0.01),
            StepResult(name="advise", status="error", duration_s=2, error="boom"),
        ]
        summary = format_summary("test_org", results)
        assert "1/2 steps succeeded" in summary
        assert "FAILED: advise" in summary
        assert "boom" in summary


class TestDiscoverOrgs:
    def test_returns_unique_sorted_orgs(self):
        with patch("sable.roster.manager.list_accounts") as mock_list:
            mock_list.return_value = [
                _make_account("@b", "org_b"),
                _make_account("@a1", "org_a"),
                _make_account("@a2", "org_a"),
            ]
            result = discover_orgs()
            assert result == ["org_a", "org_b"]
            mock_list.assert_called_once_with(active_only=True)

    def test_excludes_empty_org(self):
        with patch("sable.roster.manager.list_accounts") as mock_list:
            acc = _make_account("@x", "")
            acc.org = ""
            mock_list.return_value = [acc]
            result = discover_orgs()
            assert result == []


class TestEstimateOrgCost:
    def test_returns_positive_float(self):
        with patch("sable.roster.manager.list_accounts") as mock_list:
            mock_list.return_value = [
                _make_account("@alice", "test_org"),
                _make_account("@bob", "test_org"),
            ]
            cost = estimate_org_cost("test_org")
            assert cost > 0
            assert isinstance(cost, float)

    def test_zero_for_no_accounts(self):
        with patch("sable.roster.manager.list_accounts", return_value=[]):
            cost = estimate_org_cost("empty_org")
            assert cost == 0.0
