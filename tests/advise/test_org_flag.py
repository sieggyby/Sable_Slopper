"""Tests for --org flag on sable advise."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def conn(sable_conn):
    sable_conn.execute(
        "INSERT INTO orgs (org_id, display_name) VALUES (?, ?)",
        ("testorg", "Test Org"),
    )
    sable_conn.execute(
        "INSERT INTO orgs (org_id, display_name) VALUES (?, ?)",
        ("otherog", "Other Org"),
    )
    sable_conn.commit()
    return sable_conn


def _make_assembled_base(org_id="testorg", handle="alice"):
    return {
        "handle": handle,
        "org_id": org_id,
        "profile": {
            "tone": "casual, witty",
            "interests": "DeFi, crypto",
            "context": "crypto KOL account",
            "notes": "(not configured)",
        },
        "posts": [],
        "post_freshness": None,
        "pulse_available": False,
        "topics": [],
        "formats": [],
        "meta_scan_date": None,
        "meta_available": False,
        "meta_stale": False,
        "entities": [],
        "content_items": [],
        "tracking_last_sync": None,
        "data_freshness": {
            "pulse_last_track": None,
            "meta_last_scan": None,
            "tracking_last_sync": None,
        },
        "median_engagement": 0,
    }


def _setup_mocks(monkeypatch, conn, tmp_path, roster_dict, assembled_override=None):
    """Common setup for generate_advise tests."""
    import sable.config as sable_cfg

    monkeypatch.setattr("sable.roster.manager.load_roster", lambda: roster_dict)
    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr("sable.advise.generate.check_budget", lambda *a, **kw: None)
    monkeypatch.setattr(
        "sable.shared.paths.vault_dir",
        lambda org="": tmp_path / "vault" / (org or "default"),
    )
    assembled = assembled_override or _make_assembled_base()
    if "data_quality" not in assembled:
        assembled["data_quality"] = {"pulse_ok": True, "meta_ok": True, "platform_ok": True}
    monkeypatch.setattr("sable.advise.generate.assemble_input", lambda *a, **kw: assembled)
    monkeypatch.setattr("sable.advise.generate.synthesize",
                        lambda *a, **kw: ("brief body", 0.001, 10, 5))
    monkeypatch.setattr(sable_cfg, "load_config", lambda: {
        "platform": {"cost_caps": {"max_ai_usd_per_strategy_brief": 1.00}, "degrade_mode": "fallback"}
    })


# ─────────────────────────────────────────────────────────────────────
# Test 1: --org overrides roster org
# ─────────────────────────────────────────────────────────────────────

def test_org_flag_overrides_roster_org(conn, tmp_path, monkeypatch):
    """When --org is provided, it overrides the roster account's org."""
    from sable.advise.generate import generate_advise
    from sable.roster.models import Account, Persona, ContentSettings

    mock_account = Account(handle="alice", org="testorg", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    _setup_mocks(monkeypatch, conn, tmp_path, {"alice": mock_account})

    generate_advise("alice", org="otherog")

    # Artifact should be under otherog, not testorg
    row = conn.execute(
        "SELECT org_id FROM artifacts WHERE artifact_type='twitter_strategy_brief'"
    ).fetchone()
    assert row is not None
    assert row["org_id"] == "otherog"


# ─────────────────────────────────────────────────────────────────────
# Test 2: --org allows handle not in roster
# ─────────────────────────────────────────────────────────────────────

def test_org_flag_allows_handle_not_in_roster(conn, tmp_path, monkeypatch):
    """When --org is provided, handle need not be in roster."""
    from sable.advise.generate import generate_advise

    # Empty roster — handle "bob" does not exist
    _setup_mocks(monkeypatch, conn, tmp_path, {})

    path = generate_advise("bob", org="testorg")

    assert path  # should complete successfully
    row = conn.execute(
        "SELECT org_id FROM artifacts WHERE artifact_type='twitter_strategy_brief'"
    ).fetchone()
    assert row is not None
    assert row["org_id"] == "testorg"


# ─────────────────────────────────────────────────────────────────────
# Test 3: no --org and handle not in roster raises HANDLE_NOT_IN_ROSTER
# ─────────────────────────────────────────────────────────────────────

def test_no_org_handle_not_in_roster_raises(conn, tmp_path, monkeypatch):
    """Without --org, missing handle raises HANDLE_NOT_IN_ROSTER."""
    from sable.advise.generate import generate_advise
    from sable.platform.errors import SableError

    _setup_mocks(monkeypatch, conn, tmp_path, {})

    with pytest.raises(SableError) as exc_info:
        generate_advise("bob")

    assert exc_info.value.code == "HANDLE_NOT_IN_ROSTER"


# ─────────────────────────────────────────────────────────────────────
# Test 4: no --org and roster handle has no org raises NO_ORG_FOR_HANDLE
# ─────────────────────────────────────────────────────────────────────

def test_no_org_roster_handle_no_org_raises(conn, tmp_path, monkeypatch):
    """Without --org, roster handle with empty org raises NO_ORG_FOR_HANDLE."""
    from sable.advise.generate import generate_advise
    from sable.platform.errors import SableError
    from sable.roster.models import Account, Persona, ContentSettings

    mock_account = Account(handle="alice", org="", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    _setup_mocks(monkeypatch, conn, tmp_path, {"alice": mock_account})

    with pytest.raises(SableError) as exc_info:
        generate_advise("alice")

    assert exc_info.value.code == "NO_ORG_FOR_HANDLE"


# ─────────────────────────────────────────────────────────────────────
# Test 5: --org with org not in sable.db raises ORG_NOT_FOUND
# ─────────────────────────────────────────────────────────────────────

def test_org_flag_unknown_org_raises(conn, tmp_path, monkeypatch):
    """--org with an org_id not in sable.db raises ORG_NOT_FOUND."""
    from sable.advise.generate import generate_advise
    from sable.platform.errors import SableError
    from sable.roster.models import Account, Persona, ContentSettings

    mock_account = Account(handle="alice", org="testorg", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    _setup_mocks(monkeypatch, conn, tmp_path, {"alice": mock_account})

    with pytest.raises(SableError) as exc_info:
        generate_advise("alice", org="nonexistent")

    assert exc_info.value.code == "ORG_NOT_FOUND"


# ─────────────────────────────────────────────────────────────────────
# Test 6: --org resolves empty-org roster handle
# ─────────────────────────────────────────────────────────────────────

def test_org_flag_resolves_empty_roster_org(conn, tmp_path, monkeypatch):
    """--org provides the org when roster handle has empty org."""
    from sable.advise.generate import generate_advise
    from sable.roster.models import Account, Persona, ContentSettings

    mock_account = Account(handle="alice", org="", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    _setup_mocks(monkeypatch, conn, tmp_path, {"alice": mock_account})

    path = generate_advise("alice", org="testorg")

    assert path
    row = conn.execute(
        "SELECT org_id FROM artifacts WHERE artifact_type='twitter_strategy_brief'"
    ).fetchone()
    assert row is not None
    assert row["org_id"] == "testorg"


# ─────────────────────────────────────────────────────────────────────
# Test 7: --org="" falls through to roster (treated as None)
# ─────────────────────────────────────────────────────────────────────

def test_empty_string_org_falls_through_to_roster(conn, tmp_path, monkeypatch):
    """org='' is treated as None — falls through to roster org resolution."""
    from sable.advise.generate import generate_advise
    from sable.roster.models import Account, Persona, ContentSettings

    mock_account = Account(handle="alice", org="testorg", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    _setup_mocks(monkeypatch, conn, tmp_path, {"alice": mock_account})

    path = generate_advise("alice", org="")

    assert path
    row = conn.execute(
        "SELECT org_id FROM artifacts WHERE artifact_type='twitter_strategy_brief'"
    ).fetchone()
    assert row is not None
    assert row["org_id"] == "testorg"  # roster org used, not empty string


# ─────────────────────────────────────────────────────────────────────
# Test 8: CLI wiring — --org flag passes through to generate_advise

# ─────────────────────────────────────────────────────────────────────

def test_cli_org_flag_wiring():
    """CLI --org flag is passed to generate_advise as org= kwarg."""
    from click.testing import CliRunner
    from sable.commands.advise import advise_command

    runner = CliRunner()
    generate_calls = []

    def fake_generate(handle, **kwargs):
        generate_calls.append({"handle": handle, **kwargs})
        return "/fake/path.md"

    with patch("sable.advise.generate.generate_advise", fake_generate):
        result = runner.invoke(advise_command, ["alice", "--org", "myorg"])

    assert result.exit_code == 0, result.output
    assert len(generate_calls) == 1
    assert generate_calls[0]["org"] == "myorg"


# ─────────────────────────────────────────────────────────────────────
# Test 9: CLI without --org passes org=None
# ─────────────────────────────────────────────────────────────────────

def test_cli_no_org_flag_passes_none():
    """CLI without --org passes org=None to generate_advise."""
    from click.testing import CliRunner
    from sable.commands.advise import advise_command

    runner = CliRunner()
    generate_calls = []

    def fake_generate(handle, **kwargs):
        generate_calls.append({"handle": handle, **kwargs})
        return "/fake/path.md"

    with patch("sable.advise.generate.generate_advise", fake_generate):
        result = runner.invoke(advise_command, ["alice"])

    assert result.exit_code == 0, result.output
    assert len(generate_calls) == 1
    assert generate_calls[0]["org"] is None
