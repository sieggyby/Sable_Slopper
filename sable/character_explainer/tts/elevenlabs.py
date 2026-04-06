"""ElevenLabs TTS engine using /with-timestamps endpoint."""
from __future__ import annotations

import base64
import logging
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import httpx

from sable.character_explainer.tts.base import TTSEngine, TTSResult

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0
_RETRYABLE_STATUS = {429, 500, 502, 503}

if TYPE_CHECKING:
    from sable.character_explainer.config import CharacterProfile

_API_BASE = "https://api.elevenlabs.io/v1"


def _post_with_retry(url: str, payload: dict, api_key: str) -> httpx.Response:
    """POST to ElevenLabs with retry on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                timeout=60.0,
            )
            if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES - 1:
                delay = _INITIAL_BACKOFF * (2 ** attempt)
                logger.warning(
                    "ElevenLabs %d (attempt %d/%d), retrying in %.1fs",
                    response.status_code, attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            raise
        except httpx.TimeoutException as e:
            last_exc = e
            if attempt < _MAX_RETRIES - 1:
                delay = _INITIAL_BACKOFF * (2 ** attempt)
                logger.warning(
                    "ElevenLabs timeout (attempt %d/%d), retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
                continue
            raise
    raise last_exc  # type: ignore[misc]


class ElevenLabsEngine(TTSEngine):
    def synthesize(
        self,
        text: str,
        character: "CharacterProfile",
        output_dir: str,
        original_text: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> TTSResult:
        from sable.config import require_key
        api_key = require_key("elevenlabs_api_key")

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

        response = _post_with_retry(url, payload, api_key)
        data = response.json()

        # Log cost: ElevenLabs Turbo v2 ~$0.30/1K chars
        char_count = len(text)
        estimated_cost = char_count * 0.30 / 1000
        _log_elevenlabs_cost(org_id, estimated_cost, char_count)

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


def _log_elevenlabs_cost(
    org_id: str | None, estimated_cost: float, char_count: int
) -> None:
    """Log ElevenLabs TTS cost to sable.db. Non-fatal."""
    if not org_id:
        return
    try:
        from sable.platform.db import get_db
        from sable.platform.cost import log_cost
        conn = get_db()
        try:
            log_cost(conn, org_id, "elevenlabs_tts", estimated_cost, model="elevenlabs")
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to log ElevenLabs cost for org %s: %s", org_id, e)
