"""Tests for wojak/library.py — load_library(), get_wojak(), get_wojak_image()."""
from __future__ import annotations

import pytest
import yaml


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setenv("SABLE_WORKSPACE", str(tmp_path / "workspace"))


def _wojaks_dir(tmp_path):
    d = tmp_path / ".sable" / "wojaks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_library(tmp_path, entries: list[dict]) -> None:
    d = _wojaks_dir(tmp_path)
    (d / "_library.yaml").write_text(yaml.dump(entries, allow_unicode=True))


# ─────────────────────────────────────────────────────────────────────
# load_library
# ─────────────────────────────────────────────────────────────────────

def test_load_library_returns_seed_when_no_index(tmp_path):
    """No existing index → _ensure_library writes the seed library; returns non-empty list."""
    from sable.wojak.library import load_library
    result = load_library()
    # Seed library has 20 entries
    assert isinstance(result, list)
    assert len(result) > 0


def test_load_library_reads_yaml_entries(tmp_path):
    entries = [
        {"id": "test-wojak", "name": "Test", "emotion": "happy", "tags": [], "image_file": "test.png"},
    ]
    _write_library(tmp_path, entries)

    from sable.wojak.library import load_library
    result = load_library()
    assert len(result) == 1
    assert result[0]["id"] == "test-wojak"


# ─────────────────────────────────────────────────────────────────────
# get_wojak
# ─────────────────────────────────────────────────────────────────────

def test_get_wojak_returns_entry_by_id(tmp_path):
    entries = [
        {"id": "crying-wojak", "name": "Crying Wojak", "emotion": "sad", "tags": [], "image_file": "crying.png"},
        {"id": "chad-wojak", "name": "Chad Wojak", "emotion": "chad", "tags": [], "image_file": "chad.png"},
    ]
    _write_library(tmp_path, entries)

    from sable.wojak.library import get_wojak
    result = get_wojak("chad-wojak")
    assert result["id"] == "chad-wojak"
    assert result["emotion"] == "chad"


def test_get_wojak_raises_on_unknown_id(tmp_path):
    entries = [
        {"id": "crying-wojak", "name": "Crying", "emotion": "sad", "tags": [], "image_file": "crying.png"},
    ]
    _write_library(tmp_path, entries)

    from sable.wojak.library import get_wojak
    with pytest.raises(ValueError, match="not found"):
        get_wojak("nonexistent-id")


def test_get_wojak_raises_on_empty_library(tmp_path):
    _write_library(tmp_path, [])

    from sable.wojak.library import get_wojak
    with pytest.raises(ValueError):
        get_wojak("any-id")


# ─────────────────────────────────────────────────────────────────────
# get_wojak_image
# ─────────────────────────────────────────────────────────────────────

def test_get_wojak_image_returns_path_when_exists(tmp_path):
    wojak_entry = {"id": "test-wojak", "image_file": "test.png"}
    img_path = _wojaks_dir(tmp_path) / "test.png"
    img_path.write_bytes(b"\x89PNG")  # minimal content

    from sable.wojak.library import get_wojak_image
    result = get_wojak_image(wojak_entry)
    assert result is not None
    assert result.exists()


def test_get_wojak_image_returns_none_when_missing(tmp_path):
    wojak_entry = {"id": "ghost-wojak", "image_file": "ghost.png"}

    from sable.wojak.library import get_wojak_image
    result = get_wojak_image(wojak_entry)
    assert result is None
