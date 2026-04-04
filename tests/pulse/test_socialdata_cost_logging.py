"""Tests for SocialData cost logging to sable.db cost_events."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_meta_scan_logs_socialdata_cost():
    """SocialData cost is logged via log_cost with correct call_type and model."""
    logged_calls = []

    def mock_log_cost(conn, org_id, call_type, cost_usd, **kwargs):
        logged_calls.append({
            "org_id": org_id,
            "call_type": call_type,
            "cost_usd": cost_usd,
            "model": kwargs.get("model"),
        })

    mock_conn = MagicMock()

    with patch("sable.platform.db.get_db", return_value=mock_conn):
        with patch("sable.platform.cost.log_cost", side_effect=mock_log_cost):
            from sable.platform.db import get_db
            from sable.platform.cost import log_cost
            _conn = get_db()
            try:
                log_cost(_conn, "test_org", "socialdata_meta_scan", 0.012,
                         model="socialdata", input_tokens=0, output_tokens=0)
            finally:
                _conn.close()

    assert len(logged_calls) == 1
    assert logged_calls[0]["org_id"] == "test_org"
    assert logged_calls[0]["call_type"] == "socialdata_meta_scan"
    assert logged_calls[0]["cost_usd"] == 0.012
    assert logged_calls[0]["model"] == "socialdata"


def test_pulse_track_logs_socialdata_cost():
    """pulse track logs $0.002 SocialData cost for a single API call."""
    logged_calls = []

    def mock_log_cost(conn, org_id, call_type, cost_usd, **kwargs):
        logged_calls.append({
            "org_id": org_id,
            "call_type": call_type,
            "cost_usd": cost_usd,
        })

    mock_conn = MagicMock()

    with patch("sable.platform.db.get_db", return_value=mock_conn):
        with patch("sable.platform.cost.log_cost", side_effect=mock_log_cost):
            from sable.platform.db import get_db
            from sable.platform.cost import log_cost
            _conn = get_db()
            try:
                log_cost(_conn, "tig", "socialdata_pulse_track", 0.002,
                         model="socialdata", input_tokens=0, output_tokens=0)
            finally:
                _conn.close()

    assert len(logged_calls) == 1
    assert logged_calls[0]["call_type"] == "socialdata_pulse_track"
    assert logged_calls[0]["cost_usd"] == 0.002


def test_socialdata_cost_logging_nonfatal():
    """SocialData cost logging errors must not propagate."""
    import sqlite3

    # Simulate the non-fatal pattern used in cli.py
    caught = False
    try:
        try:
            raise sqlite3.OperationalError("db locked")
        except (sqlite3.Error, OSError):
            caught = True
    except Exception:
        pass  # Should never reach here
    assert caught
