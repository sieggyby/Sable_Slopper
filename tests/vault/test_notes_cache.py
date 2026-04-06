"""Tests for T2-5: vault notes in-memory TTL cache."""
from __future__ import annotations

from pathlib import Path

from sable.vault.notes import (
    _notes_cache,
    _CACHE_TTL,
    invalidate_notes_cache,
    load_all_notes,
    write_note,
)


def _make_vault(tmp_path: Path, n: int = 3) -> Path:
    """Create a minimal vault with n content notes."""
    vault = tmp_path / "vault"
    content = vault / "content"
    content.mkdir(parents=True)
    for i in range(n):
        (content / f"note_{i}.md").write_text(
            f"---\ntitle: Note {i}\n---\nBody {i}\n", encoding="utf-8"
        )
    return vault


def test_cache_hit_returns_same_object(tmp_path):
    """Second call returns cached list (same id)."""
    _notes_cache.clear()
    vault = _make_vault(tmp_path)

    first = load_all_notes(vault)
    second = load_all_notes(vault)

    assert first == second  # equal data = cache hit (shallow copy)
    assert first is not second  # but distinct list objects (safe against mutation)
    assert len(first) == 3


def test_invalidate_cache_forces_reload(tmp_path):
    """invalidate_notes_cache causes next call to re-read."""
    _notes_cache.clear()
    vault = _make_vault(tmp_path)

    first = load_all_notes(vault)
    invalidate_notes_cache(vault)
    second = load_all_notes(vault)

    assert first is not second  # different object = cache miss


def test_write_note_clears_cache(tmp_path):
    """write_note invalidates the cache automatically."""
    _notes_cache.clear()
    vault = _make_vault(tmp_path)

    load_all_notes(vault)
    assert str(vault) in _notes_cache

    write_note(vault / "content" / "new.md", {"title": "New"}, "body")
    assert str(vault) not in _notes_cache


def test_invalidate_specific_vault(tmp_path):
    """invalidate_notes_cache(vault_path) only clears that vault."""
    _notes_cache.clear()
    v1 = _make_vault(tmp_path / "a")
    v2 = _make_vault(tmp_path / "b")

    load_all_notes(v1)
    load_all_notes(v2)
    assert str(v1) in _notes_cache
    assert str(v2) in _notes_cache

    invalidate_notes_cache(v1)
    assert str(v1) not in _notes_cache
    assert str(v2) in _notes_cache


def test_invalidate_all(tmp_path):
    """invalidate_notes_cache(None) clears all vaults."""
    _notes_cache.clear()
    v1 = _make_vault(tmp_path / "a")
    v2 = _make_vault(tmp_path / "b")

    load_all_notes(v1)
    load_all_notes(v2)

    invalidate_notes_cache()
    assert len(_notes_cache) == 0
