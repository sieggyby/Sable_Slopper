"""AQ-32: Advise generate orchestration tests — cache, budget, dry_run."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine

from sable_platform.db.compat_conn import CompatConnection
from sable_platform.db.schema import metadata as sa_metadata
from sable.platform.errors import SableError


def _make_conn():
    engine = create_engine("sqlite:///:memory:")
    sa_metadata.create_all(engine)
    sa_conn = engine.connect()
    conn = CompatConnection(sa_conn)
    conn.execute(
        "INSERT INTO orgs (org_id, display_name) VALUES (?, ?)",
        ("testorg", "Test"),
    )
    conn.commit()
    return conn


def _mock_roster(handle="testuser", org="testorg"):
    """Roster keys are normalized (no @, lowercase)."""
    from sable.roster.models import Account
    acc = Account(handle=f"@{handle}", org=org)
    roster = {handle: acc}
    return roster, acc


def test_generate_advise_dry_run_no_api_calls(monkeypatch):
    """dry_run → returns empty string, no Claude calls."""
    conn = _make_conn()
    roster, acc = _mock_roster()

    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr(
        "sable.roster.manager.load_roster",
        lambda: roster,
    )

    with patch("sable.shared.api.call_claude_json") as mock_claude, \
         patch("sable.advise.generate._check_cache", return_value=(False, None)):
        from sable.advise.generate import generate_advise
        result = generate_advise("@testuser", dry_run=True)

    assert result == ""
    mock_claude.assert_not_called()


def test_generate_advise_cache_hit_returns_cached(monkeypatch):
    """Cache hit → returns cached path without calling Claude."""
    conn = _make_conn()
    roster, acc = _mock_roster()

    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr(
        "sable.roster.manager.load_roster",
        lambda: roster,
    )

    with patch("sable.advise.generate._check_cache", return_value=(True, "/cached/brief.md")), \
         patch("sable.shared.api.call_claude_json") as mock_claude:
        from sable.advise.generate import generate_advise
        result = generate_advise("@testuser")

    assert result == "/cached/brief.md"
    mock_claude.assert_not_called()


def test_generate_advise_unknown_org_raises(monkeypatch):
    """Unknown org → SableError(ORG_NOT_FOUND)."""
    conn = _make_conn()
    from sable.roster.models import Account
    acc = Account(handle="@nobody", org="ghost_org")
    roster = {"nobody": acc}  # normalized key

    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr(
        "sable.roster.manager.load_roster",
        lambda: roster,
    )

    from sable.advise.generate import generate_advise
    with pytest.raises(SableError, match="ORG_NOT_FOUND"):
        generate_advise("@nobody")


def test_generate_advise_no_roster_entry_raises(monkeypatch):
    """Handle not in roster + no --org → SableError."""
    conn = _make_conn()
    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr(
        "sable.roster.manager.load_roster",
        lambda: {},
    )

    from sable.advise.generate import generate_advise
    with pytest.raises(SableError):
        generate_advise("@ghost")


def test_generate_advise_budget_exceeded_raises(monkeypatch):
    """Budget exceeded with degrade_mode='error' → SableError(BUDGET_EXCEEDED) propagates."""
    conn = _make_conn()
    roster, acc = _mock_roster()

    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr(
        "sable.roster.manager.load_roster",
        lambda: roster,
    )

    # degrade_mode must be 'error' for budget to raise (default is 'fallback')
    def _mock_cfg_get(key, default=None):
        if key == "platform":
            return {"degrade_mode": "error", "cost_caps": {"max_ai_usd_per_strategy_brief": 0.20}}
        return default

    with patch("sable.advise.generate._check_cache", return_value=(False, None)), \
         patch("sable.advise.generate.check_budget",
               side_effect=SableError("BUDGET_EXCEEDED", "over budget")), \
         patch("sable.config.get", side_effect=_mock_cfg_get):
        from sable.advise.generate import generate_advise
        with pytest.raises(SableError, match="BUDGET_EXCEEDED"):
            generate_advise("@testuser")
