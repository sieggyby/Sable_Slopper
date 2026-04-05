"""Tests for character_explainer/phonetics.py."""
from __future__ import annotations

import pytest

from sable.character_explainer.phonetics import (
    align_to_script,
    apply_phonetic_corrections,
    parse_phonetic_corrections,
)


# ── parse_phonetic_corrections ───────────────────────────────────────


class TestParsePhoneticCorrections:
    def test_parses_corrections_section(self):
        md = """\
## Phonetic Corrections
- DeFi → dee-fy
- DAO → dow
"""
        result = parse_phonetic_corrections(md)
        assert result == {"DeFi": "dee-fy", "DAO": "dow"}

    def test_stops_at_next_section(self):
        md = """\
## Phonetic Corrections
- DeFi → dee-fy

## Other Section
- ignored → nope
"""
        result = parse_phonetic_corrections(md)
        assert result == {"DeFi": "dee-fy"}

    def test_no_section_returns_empty(self):
        md = "Just some text without phonetic corrections."
        assert parse_phonetic_corrections(md) == {}

    def test_asterisk_bullets(self):
        md = """\
## Phonetic Corrections
* GRVT → gravity
"""
        result = parse_phonetic_corrections(md)
        assert result == {"GRVT": "gravity"}


# ── apply_phonetic_corrections ───────────────────────────────────────


class TestApplyPhoneticCorrections:
    def test_replaces_whole_words(self):
        text = "DeFi is the future of DAO governance."
        corrections = {"DeFi": "dee-fy", "DAO": "dow"}
        result = apply_phonetic_corrections(text, corrections)
        assert "dee-fy" in result
        assert "dow" in result

    def test_does_not_replace_partial_match(self):
        text = "DeFiance is not DeFi."
        corrections = {"DeFi": "dee-fy"}
        result = apply_phonetic_corrections(text, corrections)
        assert result == "DeFiance is not dee-fy."

    def test_empty_corrections_returns_original(self):
        text = "Hello world."
        assert apply_phonetic_corrections(text, {}) == text


# ── align_to_script ──────────────────────────────────────────────────


class TestAlignToScript:
    def test_exact_match_preserves_script_text(self):
        whisper = [
            {"start": 0.0, "end": 0.5, "text": "hello"},
            {"start": 0.5, "end": 1.0, "text": "world"},
        ]
        result = align_to_script(whisper, "Hello World")
        assert result[0]["text"] == "Hello"
        assert result[1]["text"] == "World"
        assert result[0]["start"] == 0.0

    def test_whisper_hallucination_dropped(self):
        whisper = [
            {"start": 0.0, "end": 0.3, "text": "um"},
            {"start": 0.3, "end": 0.8, "text": "hello"},
        ]
        result = align_to_script(whisper, "Hello")
        assert len(result) == 1
        assert result[0]["text"] == "Hello"
