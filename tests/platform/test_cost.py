"""Tests for cost logging and budget enforcement."""
import datetime
import pytest

from sable.platform.cost import log_cost, get_weekly_spend, get_org_cost_cap, check_budget
from sable.platform.errors import SableError, BUDGET_EXCEEDED


def test_log_cost(org_conn):
    log_cost(org_conn, "testorg", "claude_call", cost_usd=0.10, model="claude-sonnet-4-6")
    row = org_conn.execute("SELECT cost_usd, model FROM cost_events").fetchone()
    assert row["cost_usd"] == pytest.approx(0.10)
    assert row["model"] == "claude-sonnet-4-6"


def test_get_weekly_spend_empty(org_conn):
    spend = get_weekly_spend(org_conn, "testorg")
    assert spend == 0.0


def test_get_weekly_spend_sums_current_week(org_conn):
    log_cost(org_conn, "testorg", "call1", cost_usd=1.00)
    log_cost(org_conn, "testorg", "call2", cost_usd=0.50)
    spend = get_weekly_spend(org_conn, "testorg")
    assert spend == pytest.approx(1.50)


def test_get_weekly_spend_includes_all_statuses(org_conn):
    log_cost(org_conn, "testorg", "call1", cost_usd=1.00, call_status="success")
    log_cost(org_conn, "testorg", "call2", cost_usd=0.25, call_status="error")
    spend = get_weekly_spend(org_conn, "testorg")
    assert spend == pytest.approx(1.25)


def test_get_org_cost_cap_default(org_conn):
    cap = get_org_cost_cap(org_conn, "testorg")
    assert cap == pytest.approx(5.00)


def test_get_org_cost_cap_from_org_config(org_conn):
    import json
    org_conn.execute(
        "UPDATE orgs SET config_json=? WHERE org_id='testorg'",
        (json.dumps({"max_ai_usd_per_org_per_week": 10.00}),),
    )
    org_conn.commit()
    cap = get_org_cost_cap(org_conn, "testorg")
    assert cap == pytest.approx(10.00)


def test_check_budget_ok(org_conn):
    log_cost(org_conn, "testorg", "call", cost_usd=1.00)
    spend, cap = check_budget(org_conn, "testorg")
    assert spend == pytest.approx(1.00)
    assert cap == pytest.approx(5.00)


def test_check_budget_exceeded_raises(org_conn):
    log_cost(org_conn, "testorg", "big_call", cost_usd=6.00)
    with pytest.raises(SableError) as exc:
        check_budget(org_conn, "testorg")
    assert exc.value.code == BUDGET_EXCEEDED


def test_check_budget_at_exact_cap_raises(org_conn):
    log_cost(org_conn, "testorg", "call", cost_usd=5.00)
    with pytest.raises(SableError) as exc:
        check_budget(org_conn, "testorg")
    assert exc.value.code == BUDGET_EXCEEDED
