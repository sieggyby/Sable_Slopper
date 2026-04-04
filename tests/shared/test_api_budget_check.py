"""Tests for budget_check parameter in call_claude_with_usage."""
from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_client():
    """Ensure the global client is cleared between tests."""
    import sable.shared.api as api_mod
    original = api_mod._client
    api_mod._client = MagicMock()
    # Mock the messages.create response
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"ok": true}')]
    mock_usage = MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50
    mock_response.usage = mock_usage
    api_mod._client.messages.create.return_value = mock_response
    yield
    api_mod._client = original


@pytest.fixture()
def mock_db_and_cost():
    """Mock get_db, check_budget, and log_cost."""
    mock_conn = MagicMock()
    mock_check = MagicMock()
    mock_log = MagicMock()
    with patch("sable.platform.db.get_db", return_value=mock_conn), \
         patch("sable.platform.cost.check_budget", mock_check), \
         patch("sable.platform.cost.log_cost", mock_log):
        yield mock_conn, mock_check, mock_log


def test_budget_check_true_calls_check_budget(mock_db_and_cost):
    """budget_check=True (default) with org_id calls check_budget + log_cost."""
    from sable.shared.api import call_claude_with_usage
    _conn, mock_check, mock_log = mock_db_and_cost

    call_claude_with_usage("test prompt", org_id="psy", call_type="test")

    mock_check.assert_called_once_with(_conn, "psy")
    mock_log.assert_called_once()
    assert mock_log.call_args[0][1] == "psy"
    assert mock_log.call_args[0][2] == "test"


def test_budget_check_false_skips_check_budget(mock_db_and_cost):
    """budget_check=False with org_id skips check_budget but still calls log_cost."""
    from sable.shared.api import call_claude_with_usage
    _conn, mock_check, mock_log = mock_db_and_cost

    call_claude_with_usage("test prompt", org_id="psy", call_type="test",
                           budget_check=False)

    mock_check.assert_not_called()
    mock_log.assert_called_once()
    assert mock_log.call_args[0][1] == "psy"
    assert mock_log.call_args[0][2] == "test"


def test_no_org_id_skips_both():
    """When org_id is None, neither check_budget nor log_cost is called."""
    from sable.shared.api import call_claude_with_usage
    with patch("sable.platform.db.get_db") as mock_get_db:
        result = call_claude_with_usage("test prompt", org_id=None)
        mock_get_db.assert_not_called()
    assert result.text == '{"ok": true}'


def test_budget_check_false_no_org_skips_both():
    """budget_check=False + org_id=None → neither called."""
    from sable.shared.api import call_claude_with_usage
    with patch("sable.platform.db.get_db") as mock_get_db:
        call_claude_with_usage("test prompt", org_id=None, budget_check=False)
        mock_get_db.assert_not_called()


def test_call_claude_json_passes_budget_check(mock_db_and_cost):
    """call_claude_json passes budget_check through to call_claude_with_usage."""
    from sable.shared.api import call_claude_json
    _conn, mock_check, mock_log = mock_db_and_cost

    call_claude_json("test", org_id="psy", budget_check=False)

    mock_check.assert_not_called()
    mock_log.assert_called_once()


def test_call_claude_passes_budget_check(mock_db_and_cost):
    """call_claude passes budget_check through to call_claude_with_usage."""
    from sable.shared.api import call_claude
    _conn, mock_check, mock_log = mock_db_and_cost

    call_claude("test", org_id="psy", budget_check=False)

    mock_check.assert_not_called()
    mock_log.assert_called_once()


def test_conn_closed_in_finally(mock_db_and_cost):
    """Connection is always closed, even with budget_check=False."""
    from sable.shared.api import call_claude_with_usage
    mock_conn, _check, _log = mock_db_and_cost

    call_claude_with_usage("test", org_id="psy", budget_check=False)

    mock_conn.close.assert_called_once()


def test_log_cost_failure_does_not_crash(mock_db_and_cost):
    """If log_cost raises, the call still returns successfully."""
    from sable.shared.api import call_claude_with_usage
    _conn, _check, mock_log = mock_db_and_cost
    mock_log.side_effect = RuntimeError("DB write failed")

    result = call_claude_with_usage("test", org_id="psy", budget_check=False)

    assert result.text == '{"ok": true}'
    mock_log.assert_called_once()
