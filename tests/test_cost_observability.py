"""Tests that org_id flows from CLI through generators to call_claude_json."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sable.roster.models import Account


def _make_account(org: str = "testorg") -> Account:
    return Account(handle="@test", display_name="Test", org=org)


# ── Meme generators ──────────────────────────────────────────────────


class TestMemeGeneratorOrgId:
    def test_generate_meme_text_passes_org_id(self, monkeypatch):
        template = {
            "id": "t", "name": "T", "description": "", "prompt_hint": "",
            "zones": [{"id": "top", "label": "Top"}],
        }
        monkeypatch.setattr("sable.meme.generator.get_template", lambda tid: template)
        monkeypatch.setattr("sable.meme.generator.build_account_context", lambda acc, **kw: "")

        captured = {}

        def fake_claude(prompt, **kw):
            captured.update(kw)
            return '{"top": "hello"}'

        monkeypatch.setattr("sable.meme.generator.call_claude_json", fake_claude)

        from sable.meme.generator import generate_meme_text
        generate_meme_text("t", _make_account(), org_id="myorg")

        assert captured["org_id"] == "myorg"
        assert captured["call_type"] == "meme_generate"
        assert captured["budget_check"] is False

    def test_suggest_template_passes_org_id(self, monkeypatch):
        monkeypatch.setattr("sable.meme.generator.load_registry", lambda: [])
        monkeypatch.setattr("sable.meme.generator.build_account_context", lambda acc, **kw: "")

        captured = {}

        def fake_claude(prompt, **kw):
            captured.update(kw)
            return '"drake"'

        monkeypatch.setattr("sable.meme.generator.call_claude_json", fake_claude)

        from sable.meme.generator import suggest_template
        suggest_template(_make_account(), org_id="myorg")

        assert captured["org_id"] == "myorg"
        assert captured["call_type"] == "meme_suggest"

    def test_generate_batch_passes_org_id(self, monkeypatch):
        monkeypatch.setattr("sable.meme.generator.load_registry", lambda: [])
        monkeypatch.setattr("sable.meme.generator.build_account_context", lambda acc, **kw: "")

        captured = {}

        def fake_claude(prompt, **kw):
            captured.update(kw)
            return '[]'

        monkeypatch.setattr("sable.meme.generator.call_claude_json", fake_claude)

        from sable.meme.generator import generate_batch
        generate_batch(_make_account(), num_memes=1, org_id="myorg")

        assert captured["org_id"] == "myorg"
        assert captured["call_type"] == "meme_batch"


# ── Wojak generator ──────────────────────────────────────────────────


class TestWojakGeneratorOrgId:
    def test_generate_scene_passes_org_id(self, monkeypatch):
        library = [{"id": "w1", "name": "W", "emotion": "sad", "tags": [], "description": ""}]
        monkeypatch.setattr("sable.wojak.generator.load_library", lambda: library)
        monkeypatch.setattr("sable.wojak.generator.build_account_context", lambda acc, **kw: "")

        captured = {}

        def fake_claude(prompt, **kw):
            captured.update(kw)
            return '{"layers": [{"wojak_id": "w1", "position": "center", "label": "x"}], "caption": ""}'

        monkeypatch.setattr("sable.wojak.generator.call_claude_json", fake_claude)

        from sable.wojak.generator import generate_scene
        generate_scene(_make_account(), org_id="myorg")

        assert captured["org_id"] == "myorg"
        assert captured["call_type"] == "wojak_generate"
        assert captured["budget_check"] is False


# ── Thumbnail ─────────────────────────────────���───────────────────────


class TestThumbnailOrgId:
    def test_get_headline_passes_org_id(self, monkeypatch):
        captured = {}

        def fake_claude(prompt, **kw):
            captured.update(kw)
            return '{"headline": "Test", "palette": "blue"}'

        monkeypatch.setattr("sable.shared.api.call_claude_json", fake_claude)

        from sable.clip.thumbnail import _get_headline_and_palette
        _get_headline_and_palette("some hint", org_id="myorg")

        assert captured["org_id"] == "myorg"
        assert captured["call_type"] == "clip_thumbnail"
        assert captured["budget_check"] is False


# ── Character explainer ──────────────────────────────────────────────


class TestExplainerOrgId:
    def test_generate_script_passes_org_id(self, monkeypatch):
        from sable.character_explainer.config import ExplainerConfig

        captured_calls = []

        def fake_claude(prompt, **kw):
            captured_calls.append(kw)
            return "This is a test script about crypto."

        monkeypatch.setattr("sable.character_explainer.script.call_claude", fake_claude)

        class FakeCharacter:
            id = "test_character"
            system_prompt = "You are a character."
            speech_quirks = []

        config = ExplainerConfig()

        from sable.character_explainer.script import generate_script
        generate_script("test topic", None, FakeCharacter(), config, org_id="myorg")

        assert len(captured_calls) == 1
        assert captured_calls[0]["org_id"] == "myorg"
        assert captured_calls[0]["call_type"] == "explainer_script"
        assert captured_calls[0]["budget_check"] is False

    def test_distill_background_passes_org_id(self, monkeypatch):
        captured = {}

        def fake_claude(prompt, **kw):
            captured.update(kw)
            return "Distilled summary."

        monkeypatch.setattr("sable.character_explainer.script.call_claude", fake_claude)

        from sable.character_explainer.script import _distill_background
        _distill_background(None, "long " * 300, "claude-sonnet-4-6", org_id="myorg")

        assert captured["org_id"] == "myorg"
        assert captured["call_type"] == "explainer_distill"


# ── CLI --org flag exists ─────────────────────────────────────────────


class TestExplainerCliOrgFlag:
    def test_character_explainer_has_org_option(self):
        from sable.character_explainer.cli import generate_cmd
        param_names = [p.name for p in generate_cmd.params]
        assert "org" in param_names
