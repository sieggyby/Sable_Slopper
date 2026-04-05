"""Tests for character_explainer/subtitles.py — karaoke ASS generation."""
from __future__ import annotations

from pathlib import Path

import pytest

from sable.character_explainer.subtitles import (
    _ass_header,
    _to_ass_color,
    _ts,
    generate_karaoke_ass,
)


class TestTimestampFormat:
    def test_zero(self):
        assert _ts(0.0) == "0:00:00.00"

    def test_fractional_seconds(self):
        assert _ts(1.5) == "0:00:01.50"

    def test_minutes(self):
        assert _ts(65.25) == "0:01:05.25"


class TestColorConversion:
    def test_named_color(self):
        assert _to_ass_color("yellow") == "&H0000FFFF"

    def test_hex_color(self):
        assert _to_ass_color("#FF0000") == "&H000000FF"

    def test_unknown_falls_back_to_yellow(self):
        assert _to_ass_color("magenta") == "&H0000FFFF"


class TestAssHeader:
    def test_contains_resolution(self):
        header = _ass_header(width=1920, height=1080)
        assert "PlayResX: 1920" in header
        assert "PlayResY: 1080" in header


class TestGenerateKaraokeAss:
    def test_creates_file_with_dialogue(self, tmp_path):
        words = [
            {"start": 0.0, "end": 0.5, "text": "Hello"},
            {"start": 0.5, "end": 1.0, "text": "World"},
            {"start": 1.0, "end": 1.5, "text": "Test"},
        ]
        out = tmp_path / "subs.ass"
        generate_karaoke_ass(words, out)
        content = out.read_text()
        assert "Dialogue:" in content
        assert "Hello" in content
        assert "World" in content

    def test_empty_words_produces_header_only(self, tmp_path):
        out = tmp_path / "subs.ass"
        generate_karaoke_ass([], out)
        content = out.read_text()
        assert "[Script Info]" in content
        assert "Dialogue:" not in content
