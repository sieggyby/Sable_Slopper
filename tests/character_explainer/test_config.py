"""Tests for character_explainer/config.py — CharacterProfile and ExplainerConfig."""
from __future__ import annotations

import pytest

from sable.character_explainer.config import (
    CharacterProfile,
    ExplainerConfig,
    ORIENTATIONS,
    PLATFORM_PRESETS,
)


# ── CharacterProfile ────────────────────────────────────────────────


class TestCharacterProfile:
    def test_minimal_construction(self):
        p = CharacterProfile(
            id="test",
            display_name="Test Character",
            system_prompt="You are a test.",
            speech_quirks=[],
            explanation_style="casual",
        )
        assert p.id == "test"
        assert p.tts_backend == "local"
        assert p.speaking_speed_modifier == 1.0
        assert p.phonetic_corrections == {}
        assert p.elevenlabs_voice_id is None
        assert p.local_voice_sample_path is None

    def test_full_construction(self):
        p = CharacterProfile(
            id="full",
            display_name="Full Character",
            system_prompt="prompt",
            speech_quirks=["heh", "giggity"],
            explanation_style="brainrot",
            tts_backend="elevenlabs",
            elevenlabs_voice_id="abc123",
            speaking_speed_modifier=1.2,
            phonetic_corrections={"DeFi": "dee-fy"},
        )
        assert p.tts_backend == "elevenlabs"
        assert p.elevenlabs_voice_id == "abc123"
        assert p.speaking_speed_modifier == 1.2
        assert p.phonetic_corrections == {"DeFi": "dee-fy"}


# ── ExplainerConfig defaults ────────────────────────────────────────


class TestExplainerConfigDefaults:
    def test_landscape_twitter_defaults(self):
        cfg = ExplainerConfig()
        assert cfg.output_width == 1280
        assert cfg.output_height == 720
        assert cfg.crf == PLATFORM_PRESETS["twitter"]["crf"]
        assert cfg.video_preset == "medium"
        assert cfg.audio_bitrate == "128k"
        assert cfg.talking_head_scale == 1280 // 4

    def test_portrait_orientation(self):
        cfg = ExplainerConfig(orientation="portrait")
        assert cfg.output_width == 720
        assert cfg.output_height == 1280
        assert cfg.talking_head_scale == 720 // 4

    def test_youtube_platform_presets(self):
        cfg = ExplainerConfig(platform="youtube")
        assert cfg.crf == 18
        assert cfg.video_preset == "slow"
        assert cfg.audio_bitrate == "192k"

    def test_discord_platform_presets(self):
        cfg = ExplainerConfig(platform="discord")
        assert cfg.crf == 28
        assert cfg.video_preset == "fast"
        assert cfg.audio_bitrate == "96k"

    def test_explicit_overrides_beat_defaults(self):
        cfg = ExplainerConfig(
            output_width=1920,
            output_height=1080,
            crf=15,
            video_preset="veryslow",
            audio_bitrate="256k",
            talking_head_scale=500,
        )
        assert cfg.output_width == 1920
        assert cfg.output_height == 1080
        assert cfg.crf == 15
        assert cfg.video_preset == "veryslow"
        assert cfg.audio_bitrate == "256k"
        assert cfg.talking_head_scale == 500

    def test_unknown_platform_falls_back_to_twitter(self):
        cfg = ExplainerConfig(platform="tiktok")
        assert cfg.crf == PLATFORM_PRESETS["twitter"]["crf"]
