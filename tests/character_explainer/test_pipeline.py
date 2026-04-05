"""Tests for character_explainer/pipeline.py — orchestration with all externals mocked."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sable.character_explainer.config import CharacterProfile, ExplainerConfig
from sable.character_explainer.tts.base import TTSResult


def _make_character() -> CharacterProfile:
    return CharacterProfile(
        id="test_char",
        display_name="Test Character",
        system_prompt="You are test.",
        speech_quirks=["heh"],
        explanation_style="casual",
        tts_backend="local",
        phonetic_corrections={},
    )


def _make_tts_result(tmp_dir: Path) -> TTSResult:
    audio = tmp_dir / "tts_output.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)
    return TTSResult(
        audio_path=str(audio),
        word_timestamps=[
            {"start": 0.0, "end": 0.5, "text": "Hello"},
            {"start": 0.5, "end": 1.0, "text": "world"},
        ],
        duration_s=1.0,
    )


class TestGenerateExplainer:
    @patch("sable.character_explainer.pipeline.generate_talking_head")
    @patch("sable.character_explainer.pipeline.generate_karaoke_ass")
    @patch("sable.character_explainer.pipeline.create_tts_engine")
    @patch("sable.character_explainer.pipeline.generate_script")
    @patch("sable.character_explainer.pipeline.load_character")
    @patch("sable.character_explainer.pipeline._resolve_bg_video", return_value="/tmp/bg.mp4")
    @patch("sable.character_explainer.pipeline._assemble_video")
    def test_pipeline_calls_all_stages(
        self,
        mock_assemble,
        mock_resolve_bg,
        mock_load_char,
        mock_gen_script,
        mock_create_tts,
        mock_gen_ass,
        mock_gen_th,
        tmp_path,
    ):
        character = _make_character()
        mock_load_char.return_value = character

        script = MagicMock()
        script.full_text = "Hello world"
        script.word_count = 2
        script.estimated_duration_s = 1.0
        mock_gen_script.return_value = script

        tts_result = _make_tts_result(tmp_path)
        mock_engine = MagicMock()
        mock_engine.synthesize.return_value = tts_result
        mock_create_tts.return_value = mock_engine

        config = ExplainerConfig(talking_head_enabled=False)
        output = tmp_path / "out.mp4"

        # Mock thumbnail imports (imported inside function body)
        with patch("sable.character_explainer.thumbnail.generate_character_thumbnail"), \
             patch("sable.character_explainer.thumbnail.generate_photo_thumbnail"):
            from sable.character_explainer.pipeline import generate_explainer
            result = generate_explainer(
                topic="test topic",
                character_id="test_char",
                output_path=output,
                config=config,
            )

        assert result == output
        mock_load_char.assert_called_once_with("test_char")
        mock_gen_script.assert_called_once()
        mock_engine.synthesize.assert_called_once()
        mock_gen_ass.assert_called_once()
        mock_assemble.assert_called_once()
