"""Local F5-TTS zero-shot voice cloning engine (replaces Coqui XTTS-v2, incompatible with Python 3.13+)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from sable.character_explainer.tts.base import TTSEngine, TTSResult

if TYPE_CHECKING:
    from sable.character_explainer.config import CharacterProfile


def _normalize_caps(text: str) -> str:
    """Lowercase 2+ letter all-caps words (emphasis caps → natural case for TTS)."""
    return re.sub(r'\b[A-Z]{2,}\b', lambda m: m.group().lower(), text)


class LocalXTTSEngine(TTSEngine):
    def synthesize(
        self,
        text: str,
        character: "CharacterProfile",
        output_dir: str,
        original_text: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> TTSResult:
        # Lazy imports — avoids error if f5-tts / soundfile not installed
        try:
            from f5_tts.api import F5TTS
        except ImportError:
            raise RuntimeError(
                "f5-tts not installed. Run: pip install f5-tts"
            )
        try:
            import soundfile as sf
        except ImportError:
            raise RuntimeError(
                "soundfile not installed. Run: pip install soundfile"
            )

        from sable.shared.ffmpeg import get_duration

        out_dir = Path(output_dir)
        audio_path = str(out_dir / "tts_output.wav")

        if not character.local_voice_sample_path:
            raise ValueError(
                f"Character '{character.id}' has no local_voice_sample_path set. "
                "Provide a voice sample WAV or use --tts-backend elevenlabs."
            )

        voice_sample = str(Path(character.local_voice_sample_path).expanduser())
        if not Path(voice_sample).exists():
            raise FileNotFoundError(f"Voice sample not found: {voice_sample}")

        # F5-TTS zero-shot voice cloning.
        # ref_text="" triggers built-in ASR transcription of the voice sample.
        tts = F5TTS()
        gen_text = _normalize_caps(text)
        wav, sr, _ = tts.infer(
            ref_file=voice_sample,
            ref_text="",   # auto-transcribe reference audio
            gen_text=gen_text,
        )
        sf.write(audio_path, wav, sr)

        # F5-TTS doesn't provide word timestamps — derive via Whisper
        from sable.clip.transcribe import transcribe
        transcript = transcribe(audio_path, model="base.en")
        word_timestamps = transcript.get("words", [])

        # Align Whisper timing to original script text if provided
        if original_text and word_timestamps:
            from sable.character_explainer.phonetics import align_to_script
            word_timestamps = align_to_script(word_timestamps, original_text)

        duration = get_duration(audio_path)

        return TTSResult(
            audio_path=audio_path,
            word_timestamps=word_timestamps,
            duration_s=duration,
        )
