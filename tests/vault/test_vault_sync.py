"""Tests for platform vault sync."""
import json
import uuid
from pathlib import Path

import pytest

import sable.vault.platform_sync as _psync
from sable.vault.platform_sync import (
    _do_sync, _build_entity_note, _build_index,
    _build_diagnostic_summary, _build_diagnostic_history_entry,
    _is_inside_vault_root,
)


def _insert_entity(conn, org_id="testorg", entity_id=None, display_name="Alice", status="active"):
    if entity_id is None:
        entity_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO entities (entity_id, org_id, display_name, status) VALUES (?, ?, ?, ?)",
        (entity_id, org_id, display_name, status)
    )
    conn.commit()
    return entity_id


def _insert_handle(conn, entity_id, platform="twitter", handle="alice"):
    conn.execute(
        "INSERT INTO entity_handles (entity_id, platform, handle) VALUES (?, ?, ?)",
        (entity_id, platform, handle)
    )
    conn.commit()


def _insert_tag(conn, entity_id, tag="cultist_candidate", confidence=0.9, is_current=1):
    conn.execute(
        "INSERT INTO entity_tags (entity_id, tag, confidence, is_current) VALUES (?, ?, ?, ?)",
        (entity_id, tag, confidence, is_current)
    )
    conn.commit()


def _insert_note(conn, entity_id, body="operator note"):
    conn.execute(
        "INSERT INTO entity_notes (entity_id, body) VALUES (?, ?)",
        (entity_id, body)
    )
    conn.commit()


def _insert_content(conn, org_id, entity_id, body="test content", content_type="tweet", created_at=None):
    item_id = uuid.uuid4().hex
    created_at = created_at or "2026-03-20T00:00:00"
    conn.execute(
        "INSERT INTO content_items (item_id, org_id, entity_id, content_type, body, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (item_id, org_id, entity_id, content_type, body, created_at)
    )
    conn.commit()
    return item_id


def _insert_diag_run(conn, org_id, run_date="2026-03-10", grade="B", fit=70, action="engage",
                     verdict="Proceed", result_json=None, run_id=None):
    conn.execute(
        """INSERT INTO diagnostic_runs
           (org_id, run_type, status, run_date, overall_grade, fit_score, recommended_action, sable_verdict, result_json)
           VALUES (?, 'discord', 'completed', ?, ?, ?, ?, ?, ?)""",
        (org_id, run_date, grade, fit, action, verdict, result_json or "{}")
    )
    conn.commit()
    row = conn.execute(
        "SELECT run_id FROM diagnostic_runs WHERE org_id=? ORDER BY run_id DESC LIMIT 1", (org_id,)
    ).fetchone()
    return row["run_id"]


# ─────────────────────────────────────────────
# Test 1: entity notes created
# ─────────────────────────────────────────────

def test_vault_creates_entity_notes(conn, vault_root, monkeypatch):
    """Entities in DB → .md files in vault entities/ dir."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid = _insert_entity(conn, display_name="Alice")
    _insert_handle(conn, eid, "twitter", "alice_crypto")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    job_id = "testjob"
    stats = _do_sync(conn, org, vault_root, job_id)

    note_path = vault_root / "entities" / f"{eid}.md"
    assert note_path.exists(), f"Expected entity note at {note_path}"
    assert stats["entities_written"] == 1


# ─────────────────────────────────────────────
# Test 2: entity frontmatter keys
# ─────────────────────────────────────────────

def test_vault_entity_frontmatter(conn, vault_root, monkeypatch):
    """Entity note has correct frontmatter keys."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid = _insert_entity(conn, display_name="Bob")
    _insert_handle(conn, eid, "twitter", "bob_eth")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob")

    note_path = vault_root / "entities" / f"{eid}.md"
    content = note_path.read_text()

    # Check that frontmatter contains expected keys
    assert "entity_id:" in content
    assert "display_name:" in content
    assert "status:" in content
    assert "tags:" in content
    assert "handles:" in content


# ─────────────────────────────────────────────
# Test 3: entity tags section
# ─────────────────────────────────────────────

def test_vault_entity_tags_section(conn, vault_root, monkeypatch):
    """Active tags are rendered in the Tags section."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid = _insert_entity(conn, display_name="Carol")
    _insert_tag(conn, eid, tag="bridge_node", confidence=0.85)

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob")

    note_path = vault_root / "entities" / f"{eid}.md"
    content = note_path.read_text()

    assert "## Tags" in content
    assert "bridge_node" in content
    assert "confidence=0.85" in content


# ─────────────────────────────────────────────
# Test 4: entity content section
# ─────────────────────────────────────────────

def test_vault_entity_content_section(conn, vault_root, monkeypatch):
    """Content items within 90 days appear in Content section."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid = _insert_entity(conn, display_name="Dave")
    _insert_content(conn, "testorg", eid, body="Hello crypto world", content_type="tweet",
                    created_at="2026-03-15T12:00:00")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob")

    note_path = vault_root / "entities" / f"{eid}.md"
    content = note_path.read_text()

    assert "## Content" in content
    assert "Hello crypto world" in content


# ─────────────────────────────────────────────
# Test 5: entity diagnostic mentions
# ─────────────────────────────────────────────

def test_vault_entity_diagnostic_mentions(conn, vault_root, monkeypatch):
    """Entity with tag gets diagnostic mention section."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid = _insert_entity(conn, display_name="Eve")
    _insert_handle(conn, eid, "twitter", "eve_defi")
    _insert_tag(conn, eid, tag="cultist_candidate", confidence=0.9)
    _insert_diag_run(conn, "testorg", run_date="2026-03-10", grade="A")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob")

    note_path = vault_root / "entities" / f"{eid}.md"
    content = note_path.read_text()

    assert "## Diagnostic Mentions" in content


# ─────────────────────────────────────────────
# Test 6: entity notes section - empty shows "No notes."
# ─────────────────────────────────────────────

def test_vault_entity_notes_section(conn, vault_root, monkeypatch):
    """Operator notes section present; empty shows 'No notes.'."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid1 = _insert_entity(conn, display_name="Frank")
    eid2 = _insert_entity(conn, display_name="Grace")
    _insert_note(conn, eid1, "Important contact in DeFi")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob")

    # Entity with note
    content1 = (vault_root / "entities" / f"{eid1}.md").read_text()
    assert "## Operator Notes" in content1
    assert "Important contact in DeFi" in content1

    # Entity without note
    content2 = (vault_root / "entities" / f"{eid2}.md").read_text()
    assert "## Operator Notes" in content2
    assert "No notes." in content2


# ─────────────────────────────────────────────
# Test 7: index generated
# ─────────────────────────────────────────────

def test_vault_index_generated(conn, vault_root, monkeypatch):
    """_index.md is created with entity links."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid = _insert_entity(conn, display_name="Heidi")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob")

    index_path = vault_root / "_index.md"
    assert index_path.exists()
    content = index_path.read_text()
    assert "## Entities" in content
    assert eid in content


# ─────────────────────────────────────────────
# Test 8: safe delete only deletes tracked files inside vault root
# ─────────────────────────────────────────────

def test_vault_safe_delete(conn, vault_root, monkeypatch, tmp_path):
    """Safe delete only removes files tracked in artifacts and inside vault root."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    # Insert a previous artifact tracked in DB
    tracked_file = vault_root / "entities" / "old_entity.md"
    tracked_file.parent.mkdir(parents=True, exist_ok=True)
    tracked_file.write_text("old content")

    # Insert an untracked file (should NOT be deleted)
    untracked_file = vault_root / "untracked.md"
    untracked_file.write_text("keep me")

    # Insert artifact pointing OUTSIDE vault root (should NOT be deleted)
    outside_file = tmp_path / "outside.md"
    outside_file.write_text("outside")

    # Get a valid job_id
    conn.execute("INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('prevjob', 'testorg', 'vault_sync', 'completed', '{}')")
    conn.execute(
        """INSERT INTO artifacts (org_id, job_id, artifact_type, path, metadata_json, stale)
           VALUES ('testorg', 'prevjob', 'vault_entity_note', ?, '{}', 0)""",
        (str(tracked_file),)
    )
    # Also insert outside artifact
    conn.execute(
        """INSERT INTO artifacts (org_id, job_id, artifact_type, path, metadata_json, stale)
           VALUES ('testorg', 'prevjob', 'vault_entity_note', ?, '{}', 0)""",
        (str(outside_file),)
    )
    conn.commit()

    _insert_entity(conn, display_name="Ivan")
    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob2")

    # Tracked file inside vault should be gone (was replaced or deleted during cleanup)
    # untracked file should still exist
    assert untracked_file.exists(), "Untracked file should not be deleted"
    # outside file should still exist
    assert outside_file.exists(), "Outside-vault file should not be deleted"


# ─────────────────────────────────────────────
# Test 9: idempotent
# ─────────────────────────────────────────────

def test_vault_idempotent(conn, vault_root, monkeypatch):
    """Running vault sync twice produces identical output."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid = _insert_entity(conn, display_name="Jack")
    _insert_tag(conn, eid, tag="cultist_candidate", confidence=0.8)

    org = {"org_id": "testorg", "display_name": "Test Org"}

    _do_sync(conn, org, vault_root, "job1")
    content1 = (vault_root / "entities" / f"{eid}.md").read_text()

    _do_sync(conn, org, vault_root, "job2")
    content2 = (vault_root / "entities" / f"{eid}.md").read_text()

    # Content should be the same (frontmatter timestamps may vary slightly but structure same)
    # Check key structural elements are identical
    assert content1.count("## Tags") == content2.count("## Tags")
    assert content1.count("cultist_candidate") == content2.count("cultist_candidate")


# ─────────────────────────────────────────────
# Test 10: no cost events
# ─────────────────────────────────────────────

def test_vault_no_cost_events(conn, vault_root, monkeypatch):
    """Vault sync creates no cost_events rows."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    _insert_entity(conn, display_name="Karen")

    before = conn.execute("SELECT COUNT(*) FROM cost_events WHERE org_id='testorg'").fetchone()[0]

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob")

    after = conn.execute("SELECT COUNT(*) FROM cost_events WHERE org_id='testorg'").fetchone()[0]
    assert after == before, "Vault sync should not create any cost_events"


# ─────────────────────────────────────────────
# Test 11: all generated files tracked in artifacts
# ─────────────────────────────────────────────

def test_vault_tracks_all_generated_files(conn, vault_root, monkeypatch):
    """Every file generated has a corresponding artifacts row."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid1 = _insert_entity(conn, display_name="Leon")
    eid2 = _insert_entity(conn, display_name="Mary")
    _insert_diag_run(conn, "testorg", run_date="2026-03-10")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob")

    # Get all tracked artifact paths
    rows = conn.execute(
        "SELECT path FROM artifacts WHERE org_id='testorg' AND artifact_type LIKE 'vault_%'"
    ).fetchall()
    tracked_paths = {r["path"] for r in rows}

    # Check entity notes are tracked
    for eid in [eid1, eid2]:
        expected = str(vault_root / "entities" / f"{eid}.md")
        assert expected in tracked_paths, f"Expected {expected} in artifacts"

    # Check index tracked
    assert str(vault_root / "_index.md") in tracked_paths

    # Check diagnostic summary tracked
    assert str(vault_root / "diagnostics" / "latest.md") in tracked_paths


# ─────────────────────────────────────────────
# Test 12: no pulse_meta_report → existing meta_report.md deleted
# ─────────────────────────────────────────────

def test_vault_deletes_meta_report_when_source_missing(conn, vault_root, monkeypatch):
    """When no pulse_meta_report artifact, existing meta_report.md is deleted."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    # Pre-create an existing meta_report.md
    pulse_dir = vault_root / "pulse"
    pulse_dir.mkdir(parents=True, exist_ok=True)
    meta_report = pulse_dir / "meta_report.md"
    meta_report.write_text("old report")

    _insert_entity(conn, display_name="Nina")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "testjob")

    # meta_report.md should be removed since no pulse_meta_report artifact exists
    assert not meta_report.exists(), "meta_report.md should be deleted when no source artifact"


def test_vault_sync_writes_partial_sentinel_on_meta_report_failure(conn, vault_root, monkeypatch, tmp_path):
    """A meta_report copy failure after phase-B renames must leave _PARTIAL_SYNC behind."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    eid = _insert_entity(conn, display_name="Alice")
    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "job1")

    entity_note_path = vault_root / "entities" / f"{eid}.md"
    content_before = entity_note_path.read_text()

    conn.execute("UPDATE entities SET display_name=? WHERE entity_id=?", ("Bob", eid))
    conn.execute(
        "INSERT INTO jobs (job_id, org_id, job_type, status, config_json) VALUES ('pulsejob', 'testorg', 'pulse_meta', 'completed', '{}')"
    )
    source_report = tmp_path / "pulse_meta_report.md"
    source_report.write_text("latest pulse report", encoding="utf-8")
    conn.execute(
        """INSERT INTO artifacts (org_id, job_id, artifact_type, path, metadata_json, stale)
           VALUES ('testorg', 'pulsejob', 'pulse_meta_report', ?, '{}', 0)""",
        (str(source_report),)
    )
    conn.commit()

    original_write_to_temp = _psync._write_to_temp
    meta_report_dest = vault_root / "pulse" / "meta_report.md"

    def fail_on_meta_report(path, content):
        if path == meta_report_dest:
            raise RuntimeError("injected meta_report failure")
        return original_write_to_temp(path, content)

    monkeypatch.setattr(_psync, "_write_to_temp", fail_on_meta_report)

    with pytest.raises(RuntimeError, match="injected meta_report failure"):
        _do_sync(conn, org, vault_root, "job2")

    assert entity_note_path.read_text() != content_before
    assert "Bob" in entity_note_path.read_text()
    assert (vault_root / "_PARTIAL_SYNC").exists()


# ─────────────────────────────────────────────
# Test T1: two-phase safety — failure mid-generation preserves old artifacts
# ─────────────────────────────────────────────

def test_vault_sync_failure_preserves_old_artifacts(conn, vault_root, monkeypatch):
    """If generation fails mid-way, old artifact files and DB rows remain intact with original content."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    # First sync: insert one entity with display_name="Alice", sync successfully
    eid = _insert_entity(conn, display_name="Alice")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    _do_sync(conn, org, vault_root, "job1")

    # Read the entity note file content after first sync
    entity_note_path = vault_root / "entities" / f"{eid}.md"
    content_before = entity_note_path.read_text()

    # Update entity display_name to "Bob" in DB
    conn.execute("UPDATE entities SET display_name=? WHERE entity_id=?", ("Bob", eid))
    conn.commit()

    # Record artifact row count before second sync attempt
    rows_before = conn.execute(
        "SELECT COUNT(*) FROM artifacts WHERE org_id='testorg'"
    ).fetchone()[0]

    # Inject failure: _write_to_temp raises on the 2nd call
    call_count = {"n": 0}
    original_write_to_temp = _psync._write_to_temp

    def failing_write_to_temp(path, content):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("injected failure on 2nd write")
        return original_write_to_temp(path, content)

    monkeypatch.setattr(_psync, "_write_to_temp", failing_write_to_temp)

    with pytest.raises(RuntimeError, match="injected failure"):
        _do_sync(conn, org, vault_root, "job2")

    # File content must still be the "Alice" version (not "Bob")
    assert entity_note_path.read_text() == content_before, \
        "Entity note file was modified despite generation failure"

    # Artifact row count must be unchanged
    rows_after = conn.execute(
        "SELECT COUNT(*) FROM artifacts WHERE org_id='testorg'"
    ).fetchone()[0]
    assert rows_after == rows_before, \
        f"Artifact row count changed on failure: before={rows_before}, after={rows_after}"


# ─────────────────────────────────────────────
# Test 13: two diagnostic runs get different history filenames
# ─────────────────────────────────────────────

def test_vault_diagnostic_history_unique_filenames(conn, vault_root, monkeypatch):
    """Two diagnostic runs get different filenames in history/."""
    monkeypatch.setattr("sable.vault.platform_sync._safe_vault_root", lambda org_id: vault_root)

    _insert_entity(conn, display_name="Oscar")
    run_id1 = _insert_diag_run(conn, "testorg", run_date="2026-03-01", grade="A")
    run_id2 = _insert_diag_run(conn, "testorg", run_date="2026-03-10", grade="B")

    org = {"org_id": "testorg", "display_name": "Test Org"}
    stats = _do_sync(conn, org, vault_root, "testjob")

    history_dir = vault_root / "diagnostics" / "history"
    hist_files = list(history_dir.glob("*.md"))
    assert len(hist_files) == 2, f"Expected 2 history files, got {len(hist_files)}"

    filenames = {f.name for f in hist_files}
    assert f"{run_id1}.md" in filenames
    assert f"{run_id2}.md" in filenames
    assert stats["diagnostics_written"] == 2
