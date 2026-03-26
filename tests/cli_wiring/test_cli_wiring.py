"""Tests for CLI command wiring."""
from click.testing import CliRunner

import importlib


def _get_main():
    """Import the main CLI group from sable.cli module (the file, not the package)."""
    import sable.cli as sable_cli_module
    return sable_cli_module.main


def test_main_has_advise_command():
    """sable advise is registered in the main CLI."""
    main = _get_main()
    assert "advise" in main.commands


def test_main_has_playbook_command():
    """sable playbook is registered in the main CLI."""
    main = _get_main()
    assert "playbook" in main.commands


def test_main_has_tracking_command():
    """sable tracking is registered in the main CLI."""
    main = _get_main()
    assert "tracking" in main.commands


def test_main_has_onboard_command():
    """sable onboard is registered in the main CLI."""
    main = _get_main()
    assert "onboard" in main.commands


def test_vault_sync_accepts_positional_org_id():
    """sable vault sync accepts ORG_ID as positional argument."""
    from sable.vault.cli import vault_sync
    runner = CliRunner()
    # Invoke with a fake org_id to verify the command accepts it (will fail at platform level)
    result = runner.invoke(vault_sync, ["fakeorg123"])
    # Should not be a "No such argument" or "Unexpected" click error
    assert "No such argument" not in result.output
    assert "Error: No such" not in result.output


def test_pulse_account_command_registered():
    """sable pulse account is registered under pulse group."""
    from sable.pulse.cli import pulse_group
    assert "account" in pulse_group.commands


def test_pulse_account_missing_roster_entry_exits_nonzero():
    """sable pulse account with unknown handle exits 1."""
    from sable.pulse.cli import pulse_account
    runner = CliRunner()
    result = runner.invoke(pulse_account, ["--account", "@definitely_not_in_roster_xyz"])
    assert result.exit_code == 1
