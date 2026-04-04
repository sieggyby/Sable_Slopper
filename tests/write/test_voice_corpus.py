"""Tests for assemble_voice_corpus — voice corpus building for --voice-check."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sable.write.generator import assemble_voice_corpus

# Patch target: profile_dir is imported at module level in generator.py
_PROFILE_DIR = "sable.write.generator.profile_dir"


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_tone_only(tmp_path):
    """When only tone.md exists, corpus includes it."""
    profile = tmp_path / "profiles" / "@test"
    _write_file(profile / "tone.md", "Speak with conviction, avoid hedging.")

    with patch(_PROFILE_DIR, return_value=profile):
        corpus = assemble_voice_corpus("@test", "org", vault_path=None)

    assert "Voice Profile" in corpus
    assert "conviction" in corpus


def test_tone_and_notes(tmp_path):
    """Both tone.md and notes.md are included."""
    profile = tmp_path / "profiles" / "@test"
    _write_file(profile / "tone.md", "Direct, punchy.")
    _write_file(profile / "notes.md", "Prefers threads over standalone.")

    with patch(_PROFILE_DIR, return_value=profile):
        corpus = assemble_voice_corpus("@test", "org", vault_path=None)

    assert "Voice Profile" in corpus
    assert "Account Notes" in corpus
    assert "threads" in corpus


def test_empty_vault(tmp_path):
    """No vault path → corpus is profile files only."""
    profile = tmp_path / "profiles" / "@test"
    _write_file(profile / "tone.md", "Tone content")

    with patch(_PROFILE_DIR, return_value=profile):
        corpus = assemble_voice_corpus("@test", "org", vault_path=None)

    assert "Tone content" in corpus
    assert "Recent Posted" not in corpus


def test_posted_by_filter(tmp_path):
    """Only vault notes posted by the handle are included."""
    profile = tmp_path / "profiles" / "@test"
    _write_file(profile / "tone.md", "Tone")

    vault = tmp_path / "vault"
    vault.mkdir()
    notes = [
        {"id": "clip-001", "title": "My Clip", "body": "Great clip",
         "posted_by": [{"account": "@test", "posted_at": "2026-01-01"}]},
        {"id": "clip-002", "title": "Other Clip", "body": "Someone else",
         "posted_by": [{"account": "@other", "posted_at": "2026-01-01"}]},
        {"id": "clip-003", "title": "No Posts", "body": "Unused", "posted_by": []},
    ]

    with patch(_PROFILE_DIR, return_value=profile), \
         patch("sable.vault.notes.load_all_notes", return_value=notes):
        corpus = assemble_voice_corpus("@test", "org", vault_path=vault)

    assert "My Clip" in corpus
    assert "Other Clip" not in corpus
    assert "No Posts" not in corpus


def test_max_notes_cap(tmp_path):
    """More than max_notes vault notes are truncated."""
    profile = tmp_path / "profiles" / "@test"
    _write_file(profile / "tone.md", "Tone")

    vault = tmp_path / "vault"
    vault.mkdir()
    notes = [
        {"id": f"clip-{i:03d}", "title": f"Clip {i}", "body": f"Body {i}",
         "posted_by": [{"account": "@test", "posted_at": f"2026-01-{i+1:02d}"}]}
        for i in range(20)
    ]

    with patch(_PROFILE_DIR, return_value=profile), \
         patch("sable.vault.notes.load_all_notes", return_value=notes):
        corpus = assemble_voice_corpus("@test", "org", vault_path=vault, max_notes=5)

    # At most 5 note entries
    assert corpus.count("**Clip") <= 5


def test_total_token_cap(tmp_path):
    """Corpus exceeding max_total_tokens is truncated."""
    profile = tmp_path / "profiles" / "@test"
    _write_file(profile / "tone.md", "X" * 20000)  # ~5000 tokens

    with patch(_PROFILE_DIR, return_value=profile):
        corpus = assemble_voice_corpus(
            "@test", "org", vault_path=None, max_total_tokens=100,
        )

    # 100 tokens * 4 chars = 400 chars max + truncation marker
    assert len(corpus) <= 405
    assert corpus.endswith("…")


def test_missing_profile_files(tmp_path):
    """Missing profile dir → empty corpus (no crash)."""
    profile = tmp_path / "profiles" / "@ghost"
    # Don't create any files

    with patch(_PROFILE_DIR, return_value=profile):
        corpus = assemble_voice_corpus("@ghost", "org", vault_path=None)

    assert corpus == ""
