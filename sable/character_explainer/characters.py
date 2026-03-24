"""Character profile loader."""
from __future__ import annotations

from pathlib import Path

import yaml

from sable.character_explainer.config import CharacterProfile

CHARACTERS_DIR = Path(__file__).parent / "characters"


def load_character(character_id: str) -> CharacterProfile:
    """Load a character profile from YAML. Raises ValueError if not found."""
    profile_path = CHARACTERS_DIR / character_id / "profile.yaml"
    if not profile_path.exists():
        available = list_characters()
        raise ValueError(
            f"Character '{character_id}' not found. Available: {', '.join(available)}"
        )

    with open(profile_path) as f:
        data = yaml.safe_load(f)

    required = {"id", "display_name", "system_prompt", "explanation_style"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Character profile '{character_id}' missing fields: {missing}")

    system_prompt = data["system_prompt"]
    corrections: dict[str, str] = {}
    voice_guide_path = CHARACTERS_DIR / character_id / "voice_guide.md"
    if voice_guide_path.exists():
        guide_text = voice_guide_path.read_text().strip()
        system_prompt = system_prompt.rstrip() + "\n\n" + guide_text
        from sable.character_explainer.phonetics import parse_phonetic_corrections
        corrections = parse_phonetic_corrections(guide_text)

    return CharacterProfile(
        id=data["id"],
        display_name=data["display_name"],
        system_prompt=system_prompt,
        speech_quirks=data.get("speech_quirks", []),
        explanation_style=data["explanation_style"],
        tts_backend=data.get("tts_backend", "local"),
        local_voice_sample_path=data.get("local_voice_sample_path"),
        elevenlabs_voice_id=data.get("elevenlabs_voice_id"),
        speaking_speed_modifier=data.get("speaking_speed_modifier", 1.0),
        image_closed_mouth=data.get("image_closed_mouth"),
        image_open_mouth=data.get("image_open_mouth"),
        image_blink=data.get("image_blink"),
        thumbnail_photo_path=data.get("thumbnail_photo_path"),
        phonetic_corrections=corrections,
    )


def list_characters() -> list[str]:
    """Return available character IDs."""
    if not CHARACTERS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in CHARACTERS_DIR.iterdir()
        if d.is_dir() and (d / "profile.yaml").exists()
    )
