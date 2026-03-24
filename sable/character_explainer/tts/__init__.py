"""TTS engine backends for character explainer."""
from __future__ import annotations

from sable.character_explainer.tts.base import TTSEngine, TTSResult
from sable.character_explainer.config import CharacterProfile, ExplainerConfig


def create_tts_engine(backend: str, character: CharacterProfile) -> TTSEngine:
    """Instantiate the correct TTS engine based on backend name."""
    if backend == "elevenlabs":
        from sable.character_explainer.tts.elevenlabs import ElevenLabsEngine
        return ElevenLabsEngine()
    else:
        from sable.character_explainer.tts.local_xtts import LocalXTTSEngine
        return LocalXTTSEngine()


__all__ = ["TTSEngine", "TTSResult", "create_tts_engine"]
