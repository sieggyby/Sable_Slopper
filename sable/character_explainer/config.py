"""Configuration dataclasses for character explainer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Twitter preferred resolutions
ORIENTATIONS: dict[str, tuple[int, int]] = {
    "landscape": (1280, 720),
    "portrait":  (720, 1280),
}

# Per-platform encoding presets.
# crf:          H.264 quality (lower = better; 18 is near-lossless, 28 is okay-for-chat)
# video_preset: libx264 speed/compression tradeoff
# audio_bitrate: AAC bitrate
# notes:        informational
PLATFORM_PRESETS: dict[str, dict] = {
    "twitter": {
        "crf": 23,
        "video_preset": "medium",
        "audio_bitrate": "128k",
        "notes": "Max 512 MB / 2:20 on Twitter/X; H.264 + AAC",
    },
    "youtube": {
        "crf": 18,
        "video_preset": "slow",
        "audio_bitrate": "192k",
        "notes": "High quality; YouTube re-encodes anyway but start clean",
    },
    "discord": {
        "crf": 28,
        "video_preset": "fast",
        "audio_bitrate": "96k",
        "notes": "8 MB free-tier limit; keep files small",
    },
    "telegram": {
        "crf": 26,
        "video_preset": "fast",
        "audio_bitrate": "128k",
        "notes": "50 MB bot limit; 2 GB user limit — balance quality vs size",
    },
}


@dataclass
class CharacterProfile:
    id: str
    display_name: str
    system_prompt: str
    speech_quirks: list[str]
    explanation_style: str
    tts_backend: str = "local"
    local_voice_sample_path: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    speaking_speed_modifier: float = 1.0
    # Stubbed image fields — wired in when character PNGs exist
    image_closed_mouth: Optional[str] = None
    image_open_mouth: Optional[str] = None
    image_blink: Optional[str] = None
    thumbnail_photo_path: Optional[str] = None
    phonetic_corrections: dict = field(default_factory=dict)


@dataclass
class ExplainerConfig:
    target_duration_seconds: int = 30
    max_script_words: int = 90
    min_script_words: int = 40
    claude_model: str = "claude-sonnet-4-6"
    fps: int = 30
    tts_backend: str = "local"
    subtitle_mode: str = "karaoke"
    background_video_path: str = ""
    talking_head_scale: int = 0       # 0 = auto (1/4 of output width)
    talking_head_enabled: bool = True

    # Orientation & platform — drive defaults for the fields below
    orientation: str = "landscape"    # "landscape" (1280×720) or "portrait" (720×1280)
    platform: str = "twitter"         # "twitter", "youtube", "discord", "telegram"

    # Explicit overrides — 0/"" means derive from orientation/platform
    output_width: int = 0
    output_height: int = 0
    crf: int = 0
    video_preset: str = ""
    audio_bitrate: str = ""

    def __post_init__(self) -> None:
        # Resolve dimensions from orientation if not explicitly set
        default_w, default_h = ORIENTATIONS.get(self.orientation, (1280, 720))
        if self.output_width == 0:
            self.output_width = default_w
        if self.output_height == 0:
            self.output_height = default_h

        # Resolve encoding params from platform if not explicitly set
        preset = PLATFORM_PRESETS.get(self.platform, PLATFORM_PRESETS["twitter"])
        if self.crf == 0:
            self.crf = preset["crf"]
        if not self.video_preset:
            self.video_preset = preset["video_preset"]
        if not self.audio_bitrate:
            self.audio_bitrate = preset["audio_bitrate"]

        # Auto talking-head scale: 1/4 of output width
        if self.talking_head_scale == 0:
            self.talking_head_scale = self.output_width // 4
