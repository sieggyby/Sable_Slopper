"""Tests for character_explainer/tts/local_xtts.py — LocalXTTSEngine."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sable.character_explainer.config import CharacterProfile
from sable.character_explainer.tts.local_xtts import LocalXTTSEngine, _normalize_caps


def _make_character(**overrides) -> CharacterProfile:
    defaults = dict(
        id="test_char",
        display_name="Test",
        system_prompt="prompt",
        speech_quirks=[],
        explanation_style="casual",
        tts_backend="local",
        local_voice_sample_path="/tmp/fake_voice.wav",
    )
    defaults.update(overrides)
    return CharacterProfile(**defaults)


# ── _normalize_caps ──────────────────────────────────────────────────


class TestNormalizeCaps:
    def test_lowercases_all_caps_words(self):
        assert _normalize_caps("This is VERY COOL") == "This is very cool"

    def test_leaves_single_letter_caps(self):
        assert _normalize_caps("I am A person") == "I am A person"

    def test_leaves_mixed_case(self):
        assert _normalize_caps("DeFi is great") == "DeFi is great"


# ── LocalXTTSEngine.synthesize ───────────────────────────────────────


class TestLocalXTTSSynthesize:
    def test_missing_voice_sample_raises(self):
        engine = LocalXTTSEngine()
        char = _make_character(local_voice_sample_path=None)
        with pytest.raises(ValueError, match="local_voice_sample_path"):
            engine.synthesize("hello", char, "/tmp")

    def test_voice_sample_not_found_raises(self, tmp_path):
        engine = LocalXTTSEngine()
        char = _make_character(local_voice_sample_path="/nonexistent/voice.wav")

        # Mock f5_tts and soundfile so the import doesn't fail
        mock_f5 = MagicMock()
        mock_sf = MagicMock()
        with patch.dict("sys.modules", {"f5_tts": mock_f5, "f5_tts.api": mock_f5, "soundfile": mock_sf}):
            with pytest.raises(FileNotFoundError, match="Voice sample not found"):
                engine.synthesize("hello", char, str(tmp_path))
