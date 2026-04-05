"""Tests for sable.meme.templates — registry loading, template lookup, validation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

import pytest

_SAMPLE_REGISTRY = [
    {
        "id": "drake",
        "name": "Drake Pointing",
        "description": "Two panel drake.",
        "zones": [
            {"id": "top", "label": "Disapproval", "x": 0.55, "y": 0.1, "w": 0.42, "h": 0.38},
            {"id": "bottom", "label": "Approval", "x": 0.55, "y": 0.55, "w": 0.42, "h": 0.38},
        ],
        "style": "minimal",
        "image_file": "drake.jpg",
        "prompt_hint": "contrast",
    },
]


class TestGetTemplate:
    def test_returns_matching_template(self, monkeypatch):
        monkeypatch.setattr("sable.meme.templates.load_registry", lambda: list(_SAMPLE_REGISTRY))
        from sable.meme.templates import get_template
        t = get_template("drake")
        assert t["id"] == "drake"
        assert t["name"] == "Drake Pointing"

    def test_raises_for_unknown_id(self, monkeypatch):
        monkeypatch.setattr("sable.meme.templates.load_registry", lambda: list(_SAMPLE_REGISTRY))
        from sable.meme.templates import get_template
        with pytest.raises(ValueError, match="not found"):
            get_template("nonexistent")


class TestValidateTextZones:
    def test_passes_when_all_zones_present(self):
        from sable.meme.templates import validate_text_zones
        template = _SAMPLE_REGISTRY[0]
        validate_text_zones(template, {"top": "a", "bottom": "b"})

    def test_raises_when_zone_missing(self):
        from sable.meme.templates import validate_text_zones
        template = _SAMPLE_REGISTRY[0]
        with pytest.raises(ValueError, match="Missing text for zone 'bottom'"):
            validate_text_zones(template, {"top": "a"})


class TestGetTemplateImage:
    def test_returns_path_when_image_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sable.meme.templates.templates_dir", lambda: tmp_path)
        (tmp_path / "drake.jpg").write_bytes(b"fake")
        from sable.meme.templates import get_template_image
        result = get_template_image(_SAMPLE_REGISTRY[0])
        assert result == tmp_path / "drake.jpg"

    def test_returns_none_when_image_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sable.meme.templates.templates_dir", lambda: tmp_path)
        from sable.meme.templates import get_template_image
        result = get_template_image(_SAMPLE_REGISTRY[0])
        assert result is None


class TestEnsureRegistry:
    def test_seeds_default_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sable.meme.templates.templates_dir", lambda: tmp_path)
        from sable.meme.templates import ensure_registry, _REGISTRY_FILE
        reg_path = tmp_path / _REGISTRY_FILE
        assert not reg_path.exists()
        ensure_registry()
        assert reg_path.exists()

    def test_does_not_overwrite_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sable.meme.templates.templates_dir", lambda: tmp_path)
        from sable.meme.templates import ensure_registry, _REGISTRY_FILE
        reg_path = tmp_path / _REGISTRY_FILE
        reg_path.write_text("custom")
        ensure_registry()
        assert reg_path.read_text() == "custom"
