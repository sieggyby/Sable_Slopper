"""Tests for sable/shared/api.py — cost logging resilience (AUDIT-5/AUDIT-7)."""
from __future__ import annotations

import logging
from unittest.mock import patch, MagicMock


def test_log_cost_failure_emits_warning_and_call_succeeds():
    """If log_cost raises, the Claude call still succeeds and a warning is logged."""
    from sable.shared import api as api_module

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text='{"ok": true}')]
    fake_usage = MagicMock()
    fake_usage.input_tokens = 100
    fake_usage.output_tokens = 50
    fake_response.usage = fake_usage

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    fake_conn = MagicMock()

    with patch.object(api_module, "get_client", return_value=fake_client), \
         patch("sable.platform.db.get_db", return_value=fake_conn), \
         patch("sable.platform.cost.check_budget"), \
         patch("sable.platform.cost.log_cost", side_effect=RuntimeError("DB write failed")), \
         patch.object(api_module, "_compute_cost", return_value=0.01):

        with patch.object(api_module.logger, "warning") as mock_warn:
            result = api_module.call_claude_with_usage(
                "test prompt", org_id="testorg", call_type="test"
            )

    # Call succeeded despite log_cost failure
    assert result.text == '{"ok": true}'
    # Warning was logged
    mock_warn.assert_called_once()
    assert "testorg" in str(mock_warn.call_args)
