"""TTS engine abstract base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sable.character_explainer.config import CharacterProfile


@dataclass
class TTSResult:
    audio_path: str
    word_timestamps: list[dict]   # {"start", "end", "text"}
    duration_s: float


class TTSEngine(ABC):
    @abstractmethod
    def synthesize(
        self,
        text: str,
        character: "CharacterProfile",
        output_dir: str,
        original_text: Optional[str] = None,
    ) -> TTSResult: ...
