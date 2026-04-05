"""Tests for sable.meme.renderer — render_meme, wrap, outline/shadow helpers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest


_DRAKE_TEMPLATE = {
    "id": "drake",
    "name": "Drake Pointing",
    "zones": [
        {"id": "top", "x": 0.55, "y": 0.1, "w": 0.42, "h": 0.38},
        {"id": "bottom", "x": 0.55, "y": 0.55, "w": 0.42, "h": 0.38},
    ],
    "style": "classic",
}


class TestWrapText:
    def test_short_text_single_line(self):
        from sable.meme.renderer import _wrap_text
        draw = MagicMock()
        font = MagicMock()
        # Every word fits: bbox width always < max_width
        draw.textbbox.return_value = (0, 0, 100, 20)
        result = _wrap_text("hello world", font, draw, 500)
        assert result == "hello world"

    def test_long_text_wraps(self):
        from sable.meme.renderer import _wrap_text
        draw = MagicMock()
        font = MagicMock()
        # First word fits, second pushes over
        def fake_bbox(pos, text, font=None):
            words = text.split()
            w = len(words) * 200
            return (0, 0, w, 20)
        draw.textbbox = fake_bbox

        result = _wrap_text("aaa bbb ccc", font, draw, 300)
        lines = result.split("\n")
        assert len(lines) >= 2


class TestDrawOutlinedText:
    def test_calls_multiline_text_multiple_times(self):
        from sable.meme.renderer import _draw_outlined_text
        draw = MagicMock()
        font = MagicMock()
        _draw_outlined_text(draw, (10, 10), "test", font, outline_width=1)
        # outline_width=1 means offsets -1..1 → 3x3=9 positions, minus center = 8 outline + 1 fill = 9
        assert draw.multiline_text.call_count == 9


class TestDrawShadowText:
    def test_calls_multiline_text_twice(self):
        from sable.meme.renderer import _draw_shadow_text
        draw = MagicMock()
        font = MagicMock()
        _draw_shadow_text(draw, (10, 10), "test", font, shadow_offset=3)
        assert draw.multiline_text.call_count == 2


class TestRenderMeme:
    def test_render_creates_output_file(self, tmp_path, monkeypatch):
        """Full render pipeline with mocked PIL and font loading."""
        from PIL import Image
        monkeypatch.setattr("sable.meme.renderer.get_template", lambda tid: _DRAKE_TEMPLATE)
        monkeypatch.setattr("sable.meme.renderer.get_template_image", lambda t: None)
        monkeypatch.setattr("sable.meme.renderer._placeholder_image",
                            lambda t: Image.new("RGBA", (800, 600), (50, 50, 50)))

        mock_font = MagicMock()
        monkeypatch.setattr("sable.meme.renderer.find_font_size",
                            lambda *a, **kw: (mock_font, 40))
        monkeypatch.setattr("sable.meme.renderer.load_font",
                            lambda *a, **kw: mock_font)
        monkeypatch.setattr("sable.meme.renderer._wrap_text", lambda text, *a, **kw: text)
        monkeypatch.setattr("sable.meme.renderer._draw_outlined_text", lambda *a, **kw: None)
        monkeypatch.setattr("sable.meme.renderer._draw_shadow_text", lambda *a, **kw: None)

        out = tmp_path / "test.png"
        from sable.meme.renderer import render_meme
        result = render_meme("drake", {"top": "no", "bottom": "yes"}, out)
        assert result == out
        assert out.exists()

    def test_render_uses_style_override(self, tmp_path, monkeypatch):
        """Style param should override template default."""
        from PIL import Image
        captured_style = []

        def fake_find_font_size(*args, style="classic", **kwargs):
            captured_style.append(style)
            return (MagicMock(), 40)

        monkeypatch.setattr("sable.meme.renderer.get_template", lambda tid: _DRAKE_TEMPLATE)
        monkeypatch.setattr("sable.meme.renderer.get_template_image", lambda t: None)
        monkeypatch.setattr("sable.meme.renderer._placeholder_image",
                            lambda t: Image.new("RGBA", (800, 600), (50, 50, 50)))
        monkeypatch.setattr("sable.meme.renderer.find_font_size", fake_find_font_size)
        monkeypatch.setattr("sable.meme.renderer.load_font", lambda *a, **kw: MagicMock())
        monkeypatch.setattr("sable.meme.renderer._wrap_text", lambda text, *a, **kw: text)
        monkeypatch.setattr("sable.meme.renderer._draw_outlined_text", lambda *a, **kw: None)
        monkeypatch.setattr("sable.meme.renderer._draw_shadow_text", lambda *a, **kw: None)

        out = tmp_path / "styled.png"
        from sable.meme.renderer import render_meme
        render_meme("drake", {"top": "a", "bottom": "b"}, out, style="modern")
        assert all(s == "modern" for s in captured_style)
