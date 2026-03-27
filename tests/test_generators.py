"""Tests for meme/generator.py and wojak/generator.py — dry-run paths."""
from __future__ import annotations

import pytest

from sable.roster.models import Account


def _make_account(handle="@testaccount") -> Account:
    return Account(handle=handle)


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setenv("SABLE_WORKSPACE", str(tmp_path / "workspace"))


# ─────────────────────────────────────────────────────────────────────
# meme/generator.py — dry_run paths
# ─────────────────────────────────────────────────────────────────────

def test_generate_meme_text_dry_run_returns_placeholder_per_zone(monkeypatch):
    account = _make_account()
    template = {
        "id": "test-template",
        "name": "Test Template",
        "description": "A test",
        "prompt_hint": "test hint",
        "zones": [
            {"id": "top", "label": "Top Text"},
            {"id": "bottom", "label": "Bottom Text"},
        ],
    }

    monkeypatch.setattr("sable.meme.generator.get_template", lambda tid: template)
    monkeypatch.setattr("sable.meme.generator.build_account_context", lambda acc, **kw: "")

    from sable.meme.generator import generate_meme_text
    result = generate_meme_text("test-template", account, dry_run=True)

    assert set(result.keys()) == {"top", "bottom"}
    assert "[DRY RUN" in result["top"]
    assert "[DRY RUN" in result["bottom"]


def test_generate_meme_text_dry_run_empty_zones(monkeypatch):
    account = _make_account()
    template = {
        "id": "no-zones",
        "name": "No Zones",
        "description": "",
        "prompt_hint": "",
        "zones": [],
    }

    monkeypatch.setattr("sable.meme.generator.get_template", lambda tid: template)
    monkeypatch.setattr("sable.meme.generator.build_account_context", lambda acc, **kw: "")

    from sable.meme.generator import generate_meme_text
    result = generate_meme_text("no-zones", account, dry_run=True)
    assert result == {}


# ─────────────────────────────────────────────────────────────────────
# wojak/generator.py — dry_run paths
# ─────────────────────────────────────────────────────────────────────

def test_generate_scene_dry_run_with_library(monkeypatch):
    account = _make_account()
    library = [
        {"id": "crying-wojak", "name": "Crying", "emotion": "sad", "tags": [], "description": ""},
        {"id": "chad-wojak", "name": "Chad", "emotion": "chad", "tags": [], "description": ""},
        {"id": "npc-wojak", "name": "NPC", "emotion": "blank", "tags": [], "description": ""},
        {"id": "boomer-wojak", "name": "Boomer", "emotion": "smug", "tags": [], "description": ""},
        {"id": "zoomer-wojak", "name": "Zoomer", "emotion": "anxious", "tags": [], "description": ""},
    ]

    monkeypatch.setattr("sable.wojak.generator.load_library", lambda: library)
    monkeypatch.setattr("sable.wojak.generator.build_account_context", lambda acc, **kw: "")

    from sable.wojak.generator import generate_scene
    result = generate_scene(account, topic="DeFi", dry_run=True)

    assert "layers" in result
    assert "caption" in result
    assert len(result["layers"]) > 0


def test_generate_scene_dry_run_empty_library(monkeypatch):
    account = _make_account()

    monkeypatch.setattr("sable.wojak.generator.load_library", lambda: [])
    monkeypatch.setattr("sable.wojak.generator.build_account_context", lambda acc, **kw: "")

    from sable.wojak.generator import generate_scene
    result = generate_scene(account, dry_run=True)

    assert result == {"layers": [], "caption": "[DRY RUN]"}


def test_generate_scene_position_validation_fixes_invalid(monkeypatch):
    """After a live Claude call, invalid positions are corrected to 'center'."""
    account = _make_account()
    library = [
        {"id": "crying-wojak", "name": "Crying", "emotion": "sad", "tags": [], "description": ""},
    ]
    # Claude returns a scene with an invalid position
    fake_response = '{"layers": [{"wojak_id": "crying-wojak", "position": "top-left-invalid", "label": "me"}], "caption": "test"}'

    monkeypatch.setattr("sable.wojak.generator.load_library", lambda: library)
    monkeypatch.setattr("sable.wojak.generator.build_account_context", lambda acc, **kw: "")
    monkeypatch.setattr("sable.wojak.generator.call_claude_json", lambda prompt, **kw: fake_response)

    from sable.wojak.generator import generate_scene
    result = generate_scene(account, dry_run=False)
    assert result["layers"][0]["position"] == "center"


# ─────────────────────────────────────────────────────────────────────
# Shared: JSON code-fence stripping (tested via meme generator live path)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ('{"top": "hello"}', {"top": "hello"}),
    ('```json\n{"top": "hello"}\n```', {"top": "hello"}),
])
def test_json_codefence_stripping(raw, expected, monkeypatch):
    account = _make_account()
    template = {
        "id": "t",
        "name": "T",
        "description": "",
        "prompt_hint": "",
        "zones": [{"id": "top", "label": "Top"}],
    }

    monkeypatch.setattr("sable.meme.generator.get_template", lambda tid: template)
    monkeypatch.setattr("sable.meme.generator.build_account_context", lambda acc, **kw: "")
    monkeypatch.setattr("sable.meme.generator.call_claude_json", lambda prompt, **kw: raw)

    from sable.meme.generator import generate_meme_text
    result = generate_meme_text("t", account, dry_run=False)
    assert result == expected
