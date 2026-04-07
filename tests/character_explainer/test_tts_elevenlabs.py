"""Tests for character_explainer/tts/elevenlabs.py — ElevenLabs TTS engine."""
from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from sable.character_explainer.config import CharacterProfile
from sable.character_explainer.tts.elevenlabs import (
    ElevenLabsEngine,
    _alignment_to_words,
)


def _make_character(**overrides) -> CharacterProfile:
    defaults = dict(
        id="test_char",
        display_name="Test",
        system_prompt="prompt",
        speech_quirks=[],
        explanation_style="casual",
        tts_backend="elevenlabs",
        elevenlabs_voice_id="voice123",
    )
    defaults.update(overrides)
    return CharacterProfile(**defaults)


# ── _alignment_to_words ─────────────────────────────────────────────


class TestAlignmentToWords:
    def test_basic_alignment(self):
        alignment = {
            "characters": list("Hi there"),
            "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        }
        words = _alignment_to_words(alignment)
        assert len(words) == 2
        assert words[0]["text"] == "Hi"
        assert words[1]["text"] == "there"
        assert words[0]["start"] == 0.0
        assert words[1]["start"] == 0.3

    def test_empty_alignment(self):
        assert _alignment_to_words({}) == []
        assert _alignment_to_words({"characters": [], "character_start_times_seconds": [], "character_end_times_seconds": []}) == []

    def test_single_word_no_space(self):
        alignment = {
            "characters": list("OK"),
            "character_start_times_seconds": [0.0, 0.1],
            "character_end_times_seconds": [0.1, 0.2],
        }
        words = _alignment_to_words(alignment)
        assert len(words) == 1
        assert words[0]["text"] == "OK"


# ── ElevenLabsEngine.synthesize ─────────────────────────────────────


class TestElevenLabsSynthesize:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        engine = ElevenLabsEngine()
        char = _make_character()
        with patch("sable.config.get", return_value=None):
            with pytest.raises(RuntimeError, match="elevenlabs_api_key"):
                engine.synthesize("hello", char, "/tmp")

    def test_missing_voice_id_raises(self):
        engine = ElevenLabsEngine()
        char = _make_character(elevenlabs_voice_id=None)
        with patch("sable.config.require_key", return_value="fake-key"):
            with pytest.raises(ValueError, match="elevenlabs_voice_id"):
                engine.synthesize("hello", char, "/tmp")

    def test_successful_synthesis(self, tmp_path):
        fake_audio = b"RIFF" + b"\x00" * 100  # fake audio bytes
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "audio_base64": base64.b64encode(fake_audio).decode(),
            "alignment": {
                "characters": list("Hi world"),
                "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
                "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            },
        }
        fake_response.raise_for_status = MagicMock()

        with patch("sable.character_explainer.tts.elevenlabs._post_with_retry", return_value=fake_response), \
             patch("sable.character_explainer.tts.elevenlabs.subprocess.run") as mock_ffmpeg, \
             patch("sable.shared.ffmpeg.get_duration", return_value=2.5), \
             patch("sable.shared.ffmpeg.require_ffmpeg", return_value="/usr/bin/ffmpeg"), \
             patch("sable.character_explainer.tts.elevenlabs._log_elevenlabs_cost"), \
             patch("sable.config.require_key", return_value="fake-key"):

            mock_ffmpeg.return_value = MagicMock(returncode=0)

            engine = ElevenLabsEngine()
            char = _make_character()
            result = engine.synthesize("Hi world", char, str(tmp_path))

            assert result.duration_s == 2.5
            assert len(result.word_timestamps) == 2
            assert result.word_timestamps[0]["text"] == "Hi"
