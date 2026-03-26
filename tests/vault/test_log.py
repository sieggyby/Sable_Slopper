"""Tests for vault/log.py posted_by contract."""
from __future__ import annotations

import pytest
from pathlib import Path


def _make_note(vault_path: Path, content_id: str) -> Path:
    """Create a minimal content note for testing."""
    content_dir = vault_path / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    note_path = content_dir / f"{content_id}.md"
    note_path.write_text(
        f"---\nid: {content_id}\ntitle: Test\ntype: clip\n---\n\nBody.\n",
        encoding="utf-8",
    )
    return note_path


def test_log_post_includes_org(tmp_path):
    """log_post() should write 'org' field into the posted_by entry."""
    from sable.vault.log import log_post
    from sable.vault.notes import read_note

    vault_path = tmp_path / "vault"
    _make_note(vault_path, "content-abc")

    result = log_post(
        content_id="content-abc",
        account="@alice",
        tweet_id="99999",
        vault_path=vault_path,
        org="testorg",
    )
    assert result is True

    note_path = vault_path / "content" / "content-abc.md"
    fm, _ = read_note(note_path)
    posted_by = fm.get("posted_by", [])
    assert len(posted_by) == 1
    entry = posted_by[0]
    assert entry.get("org") == "testorg"
    assert entry.get("account") == "@alice"
    assert entry.get("tweet_id") == "99999"
    assert "posted_at" in entry
