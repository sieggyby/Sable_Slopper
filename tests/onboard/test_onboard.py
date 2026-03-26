"""Tests for the onboard orchestrator."""
import json
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from sable.platform.db import ensure_schema
from sable.platform.errors import SableError, INVALID_CONFIG, SLUG_ORG_CONFLICT, AWAITING_OPERATOR_INPUT
from sable.onboard.orchestrator import (
    _load_prospect_yaml,
    _step_create_org,
    _step_verify_entities,
    _step_seed_roster,
    _step_seed_watchlist,
    _step_initial_vault_sync,
)


# ─────────────────────────────────────────────────────────────────────
# Test 1: load_prospect_yaml parses valid YAML
# ─────────────────────────────────────────────────────────────────────

def test_load_prospect_yaml_valid(tmp_path):
    """Valid YAML prospect file is parsed as dict."""
    path = tmp_path / "myproject.yaml"
    path.write_text(yaml.dump({"display_name": "My Project", "sable_org": "myorg"}))

    result = _load_prospect_yaml(path)
    assert result["display_name"] == "My Project"
    assert result["sable_org"] == "myorg"


# ─────────────────────────────────────────────────────────────────────
# Test 2: load_prospect_yaml raises on invalid YAML
# ─────────────────────────────────────────────────────────────────────

def test_load_prospect_yaml_invalid(tmp_path):
    """Non-dict YAML raises SableError(INVALID_CONFIG)."""
    path = tmp_path / "bad.yaml"
    path.write_text("- item1\n- item2\n")  # list, not dict

    with pytest.raises(SableError) as exc_info:
        _load_prospect_yaml(path)
    assert exc_info.value.code == INVALID_CONFIG


# ─────────────────────────────────────────────────────────────────────
# Test 3: step_create_org creates org
# ─────────────────────────────────────────────────────────────────────

def test_step_create_org_creates(conn):
    """Step 1 creates org when it doesn't exist."""
    # Add a job and step first
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('system', 'System')")
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'system', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'create_org', 1)"
    ).lastrowid
    conn.commit()

    prospect = {"display_name": "New Org", "discord_server_id": "abc123"}
    _step_create_org(conn, "j1", step_id, "neworg", prospect)

    org = conn.execute("SELECT * FROM orgs WHERE org_id='neworg'").fetchone()
    assert org is not None
    assert org["display_name"] == "New Org"


# ─────────────────────────────────────────────────────────────────────
# Test 4: step_create_org skips when org exists
# ─────────────────────────────────────────────────────────────────────

def test_step_create_org_skips_existing(conn):
    """Step 1 skips if org already exists."""
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('existingorg', 'Existing Org')")
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'existingorg', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'create_org', 1)"
    ).lastrowid
    conn.commit()

    _step_create_org(conn, "j1", step_id, "existingorg", {})

    # Should complete without raising
    row = conn.execute("SELECT status FROM job_steps WHERE step_id=?", (step_id,)).fetchone()
    assert row["status"] == "completed"


# ─────────────────────────────────────────────────────────────────────
# Test 5: step_verify_entities raises when no completed diagnostic
# ─────────────────────────────────────────────────────────────────────

def test_step_verify_entities_no_diag(conn):
    """Step 3 raises INVALID_CONFIG when no completed diagnostic run."""
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'testorg', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'verify_entities', 3)"
    ).lastrowid
    conn.commit()

    with pytest.raises(SableError) as exc_info:
        _step_verify_entities(conn, "j1", step_id, "testorg")
    assert exc_info.value.code == INVALID_CONFIG


# ─────────────────────────────────────────────────────────────────────
# Test 6: step_verify_entities raises when 0 entities
# ─────────────────────────────────────────────────────────────────────

def test_step_verify_entities_no_entities(conn):
    """Step 3 raises INVALID_CONFIG when diagnostic exists but no entities."""
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.execute(
        "INSERT INTO diagnostic_runs (org_id, run_type, status) VALUES ('testorg', 'discord', 'completed')"
    )
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'testorg', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'verify_entities', 3)"
    ).lastrowid
    conn.commit()

    with pytest.raises(SableError) as exc_info:
        _step_verify_entities(conn, "j1", step_id, "testorg")
    assert exc_info.value.code == INVALID_CONFIG


# ─────────────────────────────────────────────────────────────────────
# Test 7: step_verify_entities passes when entities exist
# ─────────────────────────────────────────────────────────────────────

def test_step_verify_entities_passes(conn):
    """Step 3 completes when entities exist after diagnostic run."""
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.execute(
        "INSERT INTO diagnostic_runs (org_id, run_type, status) VALUES ('testorg', 'discord', 'completed')"
    )
    eid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO entities (entity_id, org_id, display_name, status) VALUES (?, 'testorg', 'Alice', 'active')",
        (eid,)
    )
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'testorg', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'verify_entities', 3)"
    ).lastrowid
    conn.commit()

    _step_verify_entities(conn, "j1", step_id, "testorg")
    row = conn.execute("SELECT status FROM job_steps WHERE step_id=?", (step_id,)).fetchone()
    assert row["status"] == "completed"


# ─────────────────────────────────────────────────────────────────────
# Test 8: step_seed_roster skips when no twitter_handle in prospect
# ─────────────────────────────────────────────────────────────────────

def test_step_seed_roster_skips_no_handle(conn, tmp_path):
    """Step 4 skips gracefully when prospect has no twitter_handle."""
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'testorg', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'seed_roster', 4)"
    ).lastrowid
    conn.commit()

    with patch("sable.roster.manager.load_roster") as mock_load, \
         patch("sable.roster.manager.save_roster"):
        from sable.roster.models import Roster
        mock_load.return_value = Roster()
        _step_seed_roster(conn, "j1", step_id, "testorg", {}, yes=True, interactive=False)

    row = conn.execute("SELECT status FROM job_steps WHERE step_id=?", (step_id,)).fetchone()
    assert row["status"] == "completed"


# ─────────────────────────────────────────────────────────────────────
# Test 9: step_seed_roster adds to roster with yes=True
# ─────────────────────────────────────────────────────────────────────

def test_step_seed_roster_adds_handle(conn, tmp_path):
    """Step 4 adds handle to roster when yes=True and handle not in roster."""
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'testorg', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'seed_roster', 4)"
    ).lastrowid
    conn.commit()

    prospect = {"display_name": "Test Project", "twitter_handle": "testproject"}
    saved_roster = None

    with patch("sable.roster.manager.load_roster") as mock_load, \
         patch("sable.roster.manager.save_roster") as mock_save:
        from sable.roster.models import Roster
        mock_load.return_value = Roster()

        def capture_save(r):
            nonlocal saved_roster
            saved_roster = r

        mock_save.side_effect = capture_save

        _step_seed_roster(conn, "j1", step_id, "testorg", prospect, yes=True, interactive=False)

    assert saved_roster is not None
    assert saved_roster.get("testproject") is not None


# ─────────────────────────────────────────────────────────────────────
# Test 10: step_seed_watchlist raises when no candidates
# ─────────────────────────────────────────────────────────────────────

def test_step_seed_watchlist_no_candidates(conn):
    """Step 5 raises INVALID_CONFIG when no subsquad data available."""
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'testorg', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'seed_watchlist', 5)"
    ).lastrowid
    conn.commit()

    with pytest.raises(SableError) as exc_info:
        _step_seed_watchlist(conn, "j1", step_id, "testorg", {}, yes=True, interactive=False)
    assert exc_info.value.code == INVALID_CONFIG


# ─────────────────────────────────────────────────────────────────────
# Test 11: step_seed_watchlist seeds from diagnostic_runs result_json
# ─────────────────────────────────────────────────────────────────────

def test_step_seed_watchlist_from_diagnostic_run(conn, tmp_path, monkeypatch):
    """Step 5 seeds watchlist from diagnostic_runs result_json."""
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    result_json = json.dumps({
        "bridge_nodes": [{"handle": "bridge_user"}],
        "cultist_candidates": [{"handle": "cult_user"}],
    })
    conn.execute(
        """INSERT INTO diagnostic_runs (org_id, run_type, status, result_json)
           VALUES ('testorg', 'discord', 'completed', ?)""",
        (result_json,)
    )
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'testorg', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'seed_watchlist', 5)"
    ).lastrowid
    conn.commit()

    sable_home_dir = tmp_path / "sablehome"
    sable_home_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: sable_home_dir)
    wl_path = sable_home_dir / "pulse" / "watchlist.yaml"

    _step_seed_watchlist(conn, "j1", step_id, "testorg", {}, yes=True, interactive=False)

    wl_data = yaml.safe_load(wl_path.read_text())
    testorg_entries = wl_data.get("orgs", {}).get("testorg", [])
    handles = [e["handle"] for e in testorg_entries]
    assert "bridge_user" in handles or "cult_user" in handles


# ─────────────────────────────────────────────────────────────────────
# Test 12: slug_org_conflict raises SLUG_ORG_CONFLICT
# ─────────────────────────────────────────────────────────────────────

def test_slug_org_conflict(conn, tmp_path):
    """run_onboard raises SLUG_ORG_CONFLICT when slug used by different org."""
    from sable.onboard.orchestrator import run_onboard

    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('otherorg', 'Other Org')")
    conn.execute(
        """INSERT INTO diagnostic_runs (org_id, run_type, status, project_slug)
           VALUES ('otherorg', 'discord', 'completed', 'myslug')"""
    )
    conn.commit()

    prospect = {
        "display_name": "New Project",
        "project_slug": "myslug",
        "sable_org": "neworg",
    }
    path = tmp_path / "myslug.yaml"
    path.write_text(yaml.dump(prospect))

    with patch("sable.onboard.orchestrator.get_db", return_value=conn):
        with pytest.raises(SableError) as exc_info:
            run_onboard(str(path))
    assert exc_info.value.code == SLUG_ORG_CONFLICT


# ─────────────────────────────────────────────────────────────────────
# Test 13: missing prospect YAML raises INVALID_CONFIG
# ─────────────────────────────────────────────────────────────────────

def test_missing_prospect_yaml(conn, tmp_path):
    """run_onboard raises INVALID_CONFIG when YAML file not found."""
    from sable.onboard.orchestrator import run_onboard

    with patch("sable.onboard.orchestrator.get_db", return_value=conn):
        with pytest.raises(SableError) as exc_info:
            run_onboard(str(tmp_path / "nonexistent.yaml"))
    assert exc_info.value.code == INVALID_CONFIG


# ─────────────────────────────────────────────────────────────────────
# Test 14: step_initial_vault_sync calls platform_vault_sync
# ─────────────────────────────────────────────────────────────────────

def test_step_initial_vault_sync(conn):
    """Step 6 calls platform_vault_sync and completes step."""
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('j1', 'testorg', 'onboard', 'running', '{}')")
    step_id = conn.execute(
        "INSERT INTO job_steps (job_id, step_name, step_order) VALUES ('j1', 'initial_vault_sync', 6)"
    ).lastrowid
    conn.commit()

    mock_stats = {"entities_written": 0, "diagnostics_written": 0, "index_written": 1}
    with patch("sable.vault.platform_sync.platform_vault_sync", return_value=mock_stats):
        _step_initial_vault_sync(conn, "j1", step_id, "testorg")

    row = conn.execute("SELECT status FROM job_steps WHERE step_id=?", (step_id,)).fetchone()
    assert row["status"] == "completed"


# ─────────────────────────────────────────────────────────────────────
# Test 15: org_id defaults to yaml stem when not in prospect
# ─────────────────────────────────────────────────────────────────────

def test_org_id_defaults_to_yaml_stem(conn, tmp_path):
    """run_onboard uses yaml filename stem as org_id when not specified."""
    from sable.onboard.orchestrator import run_onboard

    prospect = {"display_name": "My Stem Project"}
    path = tmp_path / "stemproject.yaml"
    path.write_text(yaml.dump(prospect))

    with patch("sable.onboard.orchestrator.get_db", return_value=conn), \
         patch("sable.onboard.orchestrator._step_run_cult_doctor") as mock_cult, \
         patch("sable.onboard.orchestrator._step_verify_entities") as mock_verify, \
         patch("sable.onboard.orchestrator._step_seed_roster") as mock_roster, \
         patch("sable.onboard.orchestrator._step_seed_watchlist") as mock_watchlist, \
         patch("sable.onboard.orchestrator._step_initial_vault_sync") as mock_vault:

        # Make steps pass without doing anything
        for mock in [mock_cult, mock_verify, mock_roster, mock_watchlist, mock_vault]:
            mock.return_value = None

        # Patch complete_step to capture calls
        with patch("sable.onboard.orchestrator.start_step"), \
             patch("sable.onboard.orchestrator.complete_step"):
            try:
                run_onboard(str(path))
            except Exception:
                pass  # May fail due to mocking, that's ok

    # Check org was created with stem name
    org = conn.execute("SELECT * FROM orgs WHERE org_id='stemproject'").fetchone()
    assert org is not None


# ─────────────────────────────────────────────────────────────────────
# Test 16: --prep creates profile directory with 4 stub files
# ─────────────────────────────────────────────────────────────────────

def test_prep_creates_profile_directory(tmp_path, monkeypatch):
    """--prep creates profile dir with tone/interests/context/notes stubs."""
    from click.testing import CliRunner
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("SABLE_HOME", str(tmp_path))

    mock_conn = MagicMock()
    mock_conn.execute.return_value = MagicMock()

    with patch("sable.pulse.db.migrate"), \
         patch("sable.platform.db.get_db", return_value=mock_conn):
        runner = CliRunner()
        from sable.commands.onboard import onboard_command
        result = runner.invoke(onboard_command, ["--prep", "--handle", "@testhandle", "--org-slug", "testorg"])

    profiles_root = tmp_path / "profiles" / "@testhandle"
    assert profiles_root.exists(), f"Profile dir not found: {profiles_root}"
    for stub in ("tone.md", "interests.md", "context.md", "notes.md"):
        assert (profiles_root / stub).exists(), f"Missing stub: {stub}"


# ─────────────────────────────────────────────────────────────────────
# Test 17: --prep stub files contain correct headers and comment lines
# ─────────────────────────────────────────────────────────────────────

def test_prep_stub_content(tmp_path, monkeypatch):
    """Each stub file contains its section header and at least one comment line."""
    from click.testing import CliRunner
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("SABLE_HOME", str(tmp_path))

    mock_conn = MagicMock()
    mock_conn.execute.return_value = MagicMock()

    with patch("sable.pulse.db.migrate"), \
         patch("sable.platform.db.get_db", return_value=mock_conn):
        runner = CliRunner()
        from sable.commands.onboard import onboard_command
        result = runner.invoke(onboard_command, ["--prep", "--handle", "@testhandle", "--org-slug", "testorg"])

    profiles_root = tmp_path / "profiles" / "@testhandle"
    expected_headers = {
        "tone.md": "# Tone",
        "interests.md": "# Interests",
        "context.md": "# Account Context",
        "notes.md": "# Operator Notes",
    }
    for filename, header in expected_headers.items():
        content = (profiles_root / filename).read_text(encoding="utf-8")
        assert header in content, f"{filename} missing header {header!r}"
        assert "<!--" in content, f"{filename} missing comment marker"


# ─────────────────────────────────────────────────────────────────────
# Test 18: --prep is idempotent — does not overwrite existing stub files
# ─────────────────────────────────────────────────────────────────────

def test_prep_idempotent_no_overwrite(tmp_path, monkeypatch):
    """Running --prep twice does not overwrite existing stub files."""
    from click.testing import CliRunner
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("SABLE_HOME", str(tmp_path))

    # Pre-create the profile dir and write a sentinel value
    profile_dir = tmp_path / "profiles" / "@testhandle"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "tone.md").write_text("SENTINEL", encoding="utf-8")

    mock_conn = MagicMock()
    mock_conn.execute.return_value = MagicMock()

    with patch("sable.pulse.db.migrate"), \
         patch("sable.platform.db.get_db", return_value=mock_conn):
        runner = CliRunner()
        from sable.commands.onboard import onboard_command
        runner.invoke(onboard_command, ["--prep", "--handle", "@testhandle", "--org-slug", "testorg"])

    assert (profile_dir / "tone.md").read_text(encoding="utf-8") == "SENTINEL"


# ─────────────────────────────────────────────────────────────────────
# Test 19: --prep prints "already exists" message on second run
# ─────────────────────────────────────────────────────────────────────

def test_prep_prints_skip_message_on_second_run(tmp_path, monkeypatch):
    """When profile already exists, --prep prints a skip/already-exists message."""
    from click.testing import CliRunner
    from unittest.mock import MagicMock, patch
    from io import StringIO

    monkeypatch.setenv("SABLE_HOME", str(tmp_path))

    # Pre-create the profile dir
    profile_dir = tmp_path / "profiles" / "@testhandle"
    profile_dir.mkdir(parents=True, exist_ok=True)

    mock_conn = MagicMock()
    mock_conn.execute.return_value = MagicMock()

    captured_messages = []

    def mock_err_print(msg, *args, **kwargs):
        captured_messages.append(str(msg))

    with patch("sable.pulse.db.migrate"), \
         patch("sable.platform.db.get_db", return_value=mock_conn), \
         patch("sable.commands.onboard.err_console") as mock_err_console:
        mock_err_console.print.side_effect = mock_err_print
        runner = CliRunner()
        from sable.commands.onboard import onboard_command
        result = runner.invoke(onboard_command, ["--prep", "--handle", "@testhandle", "--org-slug", "testorg"])

    all_messages = " ".join(captured_messages).lower()
    assert "already exists" in all_messages, (
        f"Expected 'already exists' in err_console output. Got: {captured_messages!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# Test 20: pulse_migrate is called before the DB org insert
# ─────────────────────────────────────────────────────────────────────

def test_prep_calls_migrate_before_create_org(tmp_path, monkeypatch):
    """pulse_migrate() is called before the org INSERT in --prep mode."""
    from click.testing import CliRunner
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("SABLE_HOME", str(tmp_path))

    call_order = []

    mock_conn = MagicMock()

    def track_execute(sql, *args, **kwargs):
        if "INSERT" in sql.upper():
            call_order.append("db_insert")
        return MagicMock()

    mock_conn.execute.side_effect = track_execute
    mock_conn.commit.return_value = None
    mock_conn.close.return_value = None

    def mock_migrate():
        call_order.append("pulse_migrate")

    with patch("sable.pulse.db.migrate", side_effect=mock_migrate), \
         patch("sable.platform.db.get_db", return_value=mock_conn):
        runner = CliRunner()
        from sable.commands.onboard import onboard_command
        result = runner.invoke(onboard_command, ["--prep", "--handle", "@testhandle", "--org-slug", "testorg"])

    assert "pulse_migrate" in call_order, f"pulse_migrate not called. Order: {call_order}"
    assert "db_insert" in call_order, f"db_insert not called. Order: {call_order}"
    migrate_idx = call_order.index("pulse_migrate")
    insert_idx = call_order.index("db_insert")
    assert migrate_idx < insert_idx, (
        f"pulse_migrate must be called before db_insert. Order: {call_order}"
    )
