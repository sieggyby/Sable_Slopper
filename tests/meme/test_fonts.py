"""Tests for sable.meme.fonts — font loading and auto-sizing."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestLoadFont:
    def test_classic_style_tries_impact(self, monkeypatch):
        """Classic style should attempt Impact font names."""
        tried_names = []

        def fake_find(names):
            tried_names.extend(names)
            return None

        monkeypatch.setattr("sable.meme.fonts._find_font", fake_find)
        monkeypatch.setattr("sable.meme.fonts.ImageFont.truetype",
                            MagicMock(side_effect=OSError("no font")))
        monkeypatch.setattr("sable.meme.fonts.ImageFont.load_default",
                            MagicMock(return_value="default_font"))

        from sable.meme.fonts import load_font
        load_font("classic", 40)
        assert any("Impact" in n for n in tried_names)

    def test_modern_style_tries_bold_then_arial(self, monkeypatch):
        tried_names = []

        def fake_find(names):
            tried_names.extend(names)
            return None

        monkeypatch.setattr("sable.meme.fonts._find_font", fake_find)
        monkeypatch.setattr("sable.meme.fonts.ImageFont.truetype",
                            MagicMock(side_effect=OSError("no font")))
        monkeypatch.setattr("sable.meme.fonts.ImageFont.load_default",
                            MagicMock(return_value="default_font"))

        from sable.meme.fonts import load_font
        load_font("modern", 40)
        # Should include bold names
        assert any("Bold" in n for n in tried_names)

    def test_falls_back_to_default(self, monkeypatch):
        monkeypatch.setattr("sable.meme.fonts._find_font", lambda names: None)
        monkeypatch.setattr("sable.meme.fonts.ImageFont.truetype",
                            MagicMock(side_effect=OSError("no font")))
        sentinel = MagicMock()
        monkeypatch.setattr("sable.meme.fonts.ImageFont.load_default",
                            MagicMock(return_value=sentinel))

        from sable.meme.fonts import load_font
        result = load_font("classic", 40)
        assert result is sentinel

    def test_loads_truetype_when_path_found(self, monkeypatch, tmp_path):
        font_path = tmp_path / "Impact.ttf"
        monkeypatch.setattr("sable.meme.fonts._find_font", lambda names: font_path)
        mock_truetype = MagicMock(return_value="loaded_font")
        monkeypatch.setattr("sable.meme.fonts.ImageFont.truetype", mock_truetype)

        from sable.meme.fonts import load_font
        result = load_font("classic", 60)
        mock_truetype.assert_called_once_with(str(font_path), 60)
        assert result == "loaded_font"


class TestFindFontSize:
    def test_returns_largest_fitting_size(self, monkeypatch):
        """Should iterate from large to small, returning first fit."""
        call_log = []

        def fake_load(style, size):
            call_log.append(size)
            return MagicMock()

        monkeypatch.setattr("sable.meme.fonts.load_font", fake_load)

        draw = MagicMock()
        # Return a bbox that fits for size <= 40 (w=200, h=50)
        def fake_bbox(pos, text, font=None):
            sz = call_log[-1] if call_log else 80
            if sz <= 40:
                return (0, 0, 200, 50)  # fits in 300x100
            return (0, 0, 500, 150)  # too big

        draw.multiline_textbbox = fake_bbox

        from sable.meme.fonts import find_font_size
        font, size = find_font_size(draw, "test", max_width=300, max_height=100,
                                     start_size=80, min_size=20)
        assert size == 40

    def test_returns_min_size_when_nothing_fits(self, monkeypatch):
        monkeypatch.setattr("sable.meme.fonts.load_font",
                            lambda style, size: MagicMock())
        draw = MagicMock()
        draw.multiline_textbbox.return_value = (0, 0, 9999, 9999)

        from sable.meme.fonts import find_font_size
        font, size = find_font_size(draw, "huge text", max_width=50, max_height=50,
                                     start_size=80, min_size=20)
        assert size == 20
