"""ElevenLabs TTS engine using /with-timestamps endpoint."""
from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import httpx

from sable.character_explainer.tts.base import TTSEngine, TTSResult

if TYPE_CHECKING:
    from sable.character_explainer.config import CharacterProfile

_API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsEngine(TTSEngine):
    def synthesize(
        self,
        text: str,
        character: "CharacterProfile",
        output_dir: str,
        original_text: Optional[str] = None,
    ) -> TTSResult:
        api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY environment variable not set."
            )

        voice_id = character.elevenlabs_voice_id
        if not voice_id:
            raise ValueError(
                f"Character '{character.id}' has no elevenlabs_voice_id set."
            )

        out_dir = Path(output_dir)
        mp3_path = out_dir / "tts_output.mp3"
        wav_path = out_dir / "tts_output.wav"

        url = f"{_API_BASE}/text-to-speech/{voice_id}/with-timestamps"
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "speed": character.speaking_speed_modifier,
            },
        }

        response = httpx.post(
            url,
            json=payload,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()

        # Decode base64 audio
        audio_b64 = data.get("audio_base64", "")
        mp3_path.write_bytes(base64.b64decode(audio_b64))

        # Convert mp3 → wav via ffmpeg
        from sable.shared.ffmpeg import require_ffmpeg
        subprocess.run(
            [require_ffmpeg(), "-y", "-i", str(mp3_path),
             "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1",
             str(wav_path)],
            check=True,
            capture_output=True,
        )

        # Parse character-level alignment → word-level timestamps
        alignment = data.get("alignment", {})
        word_timestamps = _alignment_to_words(alignment)

        from sable.shared.ffmpeg import get_duration
        duration = get_duration(wav_path)

        return TTSResult(
            audio_path=str(wav_path),
            word_timestamps=word_timestamps,
            duration_s=duration,
        )


def _alignment_to_words(alignment: dict) -> list[dict]:
    """Convert ElevenLabs character-level alignment to word-level dicts."""
    chars = alignment.get("characters", [])
    char_starts = alignment.get("character_start_times_seconds", [])
    char_ends = alignment.get("character_end_times_seconds", [])

    if not chars or not char_starts or not char_ends:
        return []

    words: list[dict] = []
    current_chars: list[str] = []
    current_start: float | None = None
    current_end: float = 0.0

    for ch, start, end in zip(chars, char_starts, char_ends):
        if ch == " " or ch == "":
            if current_chars:
                word = "".join(current_chars).strip()
                if word:
                    words.append({"start": current_start, "end": current_end, "text": word})
                current_chars = []
                current_start = None
        else:
            if current_start is None:
                current_start = start
            current_chars.append(ch)
            current_end = end

    # Flush last word
    if current_chars:
        word = "".join(current_chars).strip()
        if word:
            words.append({"start": current_start, "end": current_end, "text": word})

    return words
