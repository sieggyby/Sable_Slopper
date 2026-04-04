"""Tests for churn intervention playbook generation."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest

from sable.platform.db import ensure_schema
from sable.platform.errors import SableError
from sable.churn.interventions import generate_playbook, SOFT_CAP, InterventionResult

# Lazy imports in generate_playbook — patch at source
_BUDGET = "sable.platform.cost.check_budget"
_CLAUDE = "sable.shared.api.call_claude_json"


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test')")
    conn.commit()
    return conn


SAMPLE_MEMBER = {
    "handle": "@alice",
    "decay_score": 0.7,
    "topics": ["DeFi", "governance"],
    "last_active": "2026-03-15",
    "role": "core_contributor",
    "notes": "Was active in governance forum.",
}

CLAUDE_RESPONSE = json.dumps({
    "handle": "@alice",
    "interest_tags": ["defi", "governance", "dao", "voting"],
    "role_recommendation": "Governance delegate",
    "spotlight_suggestion": "Feature in weekly governance recap",
    "engagement_prompts": [
        "Ask about the new fee switch proposal",
        "Invite to governance call",
        "Share their past proposal impact stats",
    ],
    "urgency": "high",
})


def test_single_member_playbook():
    """Single member → one Claude call, one result."""
    conn = _make_conn()
    with patch(_BUDGET), patch(_CLAUDE, return_value=CLAUDE_RESPONSE):
        results = generate_playbook("testorg", [SAMPLE_MEMBER], conn)

    assert len(results) == 1
    r = results[0]
    assert r.handle == "@alice"
    assert len(r.interest_tags) == 4
    assert r.role_recommendation == "Governance delegate"
    assert r.urgency == "high"
    assert len(r.engagement_prompts) == 3
    assert r.error is None


def test_multiple_members():
    """Multiple members → one call per member."""
    conn = _make_conn()
    members = [
        {**SAMPLE_MEMBER, "handle": f"@user{i}"}
        for i in range(3)
    ]
    with patch(_BUDGET), patch(_CLAUDE, return_value=CLAUDE_RESPONSE) as mock_call:
        results = generate_playbook("testorg", members, conn)

    assert len(results) == 3
    assert mock_call.call_count == 3


def test_budget_gate_fires():
    """check_budget raises → SableError propagates."""
    conn = _make_conn()
    with patch(_BUDGET, side_effect=SableError("BUDGET_EXCEEDED", "over budget")):
        with pytest.raises(SableError, match="BUDGET_EXCEEDED"):
            generate_playbook("testorg", [SAMPLE_MEMBER], conn)


def test_dry_run_no_calls():
    """dry_run → empty list, no API calls."""
    conn = _make_conn()
    with patch(_CLAUDE) as mock_call:
        results = generate_playbook("testorg", [SAMPLE_MEMBER], conn, dry_run=True)

    assert results == []
    mock_call.assert_not_called()


def test_soft_cap_exceeded_without_force():
    """>SOFT_CAP members without --force → error."""
    conn = _make_conn()
    members = [{"handle": f"@u{i}"} for i in range(SOFT_CAP + 1)]
    with pytest.raises(SableError, match="CHURN_CAP_EXCEEDED"):
        generate_playbook("testorg", members, conn)


def test_soft_cap_exceeded_with_force():
    """>SOFT_CAP members with --force → proceeds."""
    conn = _make_conn()
    members = [{"handle": f"@u{i}"} for i in range(SOFT_CAP + 1)]
    with patch(_BUDGET), patch(_CLAUDE, return_value=CLAUDE_RESPONSE):
        results = generate_playbook("testorg", members, conn, force=True)
    assert len(results) == SOFT_CAP + 1


def test_empty_members():
    """Empty at-risk list → empty result."""
    conn = _make_conn()
    results = generate_playbook("testorg", [], conn)
    assert results == []


def test_claude_failure_captured():
    """Claude call failure → result with error, not crash."""
    conn = _make_conn()
    with patch(_BUDGET), patch(_CLAUDE, side_effect=ValueError("bad json")):
        results = generate_playbook("testorg", [SAMPLE_MEMBER], conn)

    assert len(results) == 1
    assert results[0].error is not None
    assert "bad json" in results[0].error


def test_missing_fields_use_defaults():
    """Member dict with missing fields → uses defaults, no crash."""
    conn = _make_conn()
    minimal_member = {"handle": "@bob"}
    with patch(_BUDGET), patch(_CLAUDE, return_value=CLAUDE_RESPONSE):
        results = generate_playbook("testorg", [minimal_member], conn)
    assert len(results) == 1
    assert results[0].handle == "@bob"


def test_sable_error_from_claude_propagates():
    """SableError raised during Claude call → propagates (not captured as error)."""
    conn = _make_conn()
    with patch(_BUDGET), \
         patch(_CLAUDE, side_effect=SableError("API_ERROR", "quota exceeded")):
        with pytest.raises(SableError, match="API_ERROR"):
            generate_playbook("testorg", [SAMPLE_MEMBER], conn)


def test_claude_returns_non_object_json():
    """Claude returns JSON array instead of object → captured as error."""
    conn = _make_conn()
    with patch(_BUDGET), patch(_CLAUDE, return_value="[]"):
        results = generate_playbook("testorg", [SAMPLE_MEMBER], conn)
    assert len(results) == 1
    assert results[0].error is not None
    assert "Expected JSON object" in results[0].error
