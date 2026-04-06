"""AQ-30: Tests for vault/notes.py — read/write frontmatter, load_all_notes."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from sable.vault.notes import read_note, write_note, read_frontmatter, load_all_notes


def test_read_note_valid_frontmatter(tmp_path):
    """Note with valid YAML frontmatter → parsed dict + body."""
    note = tmp_path / "test.md"
    note.write_text("---\nid: clip_001\ntype: clip\n---\n\nBody text here.\n")
    fm, body = read_note(note)
    assert fm["id"] == "clip_001"
    assert fm["type"] == "clip"
    assert "Body text here." in body


def test_read_note_no_frontmatter(tmp_path):
    """Note without frontmatter → empty dict, full content as body."""
    note = tmp_path / "plain.md"
    note.write_text("Just plain markdown.\n")
    fm, body = read_note(note)
    assert fm == {}
    assert "Just plain markdown." in body


def test_read_note_empty_frontmatter(tmp_path):
    """Note with empty frontmatter block → empty dict."""
    note = tmp_path / "empty_fm.md"
    note.write_text("---\n---\n\nBody.\n")
    fm, body = read_note(note)
    assert fm == {}
    assert "Body." in body


def test_read_frontmatter_returns_dict(tmp_path):
    """read_frontmatter convenience function."""
    note = tmp_path / "fm.md"
    note.write_text("---\nid: m1\ntype: meme\n---\n\nContent.\n")
    fm = read_frontmatter(note)
    assert fm["id"] == "m1"


def test_write_note_roundtrip(tmp_path):
    """write_note → read_note roundtrip preserves data."""
    note = tmp_path / "roundtrip.md"
    write_note(note, {"id": "rt1", "type": "clip"}, "Some body.")
    fm, body = read_note(note)
    assert fm["id"] == "rt1"
    assert "Some body." in body


def test_load_all_notes_valid(tmp_path):
    """load_all_notes finds notes in content/ subdirectory."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    note = content_dir / "clip_001.md"
    note.write_text("---\nid: clip_001\ntype: clip\n---\n\nBody.\n")

    results = load_all_notes(tmp_path)
    assert len(results) == 1
    assert results[0]["id"] == "clip_001"
    assert "_note_path" in results[0]


def test_load_all_notes_malformed_yaml_skipped(tmp_path, caplog):
    """Malformed YAML in a note → skipped with warning, not crash."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    bad = content_dir / "bad.md"
    bad.write_text("---\n: : invalid yaml [[\n---\n\nBody.\n")
    good = content_dir / "good.md"
    good.write_text("---\nid: good\n---\n\nOK.\n")

    with caplog.at_level(logging.WARNING):
        results = load_all_notes(tmp_path)

    assert len(results) == 1
    assert results[0]["id"] == "good"
    assert "Skipping malformed note" in caplog.text


def test_load_all_notes_empty_vault(tmp_path):
    """No content/ directory → empty list."""
    results = load_all_notes(tmp_path)
    assert results == []


def test_load_all_notes_nested_dirs(tmp_path):
    """Notes in nested subdirs under content/ are found."""
    nested = tmp_path / "content" / "clips" / "2026"
    nested.mkdir(parents=True)
    note = nested / "deep.md"
    note.write_text("---\nid: deep1\n---\n")

    results = load_all_notes(tmp_path)
    assert len(results) == 1
    assert results[0]["id"] == "deep1"
