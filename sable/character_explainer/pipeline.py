"""Character explainer video pipeline orchestrator."""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from sable.character_explainer.characters import load_character
from sable.character_explainer.config import ExplainerConfig
from sable.character_explainer.phonetics import apply_phonetic_corrections, parse_phonetic_corrections
from sable.character_explainer.script import generate_script
from sable.character_explainer.subtitles import generate_karaoke_ass
from sable.character_explainer.talking_head import TalkingHeadResult, generate_talking_head
from sable.character_explainer.tts import create_tts_engine
from sable.shared.ffmpeg import extract_clip, get_duration, require_ffmpeg
from sable.shared.paths import brainrot_dir


def generate_explainer(
    topic: str,
    character_id: str,
    output_path: str | Path,
    background: Optional[str] = None,
    config: Optional[ExplainerConfig] = None,
    org_id: str | None = None,
) -> Path:
    """
    Full pipeline: script → TTS → subtitles → video assembly.

    Returns the path to the output video file.
    """
    if config is None:
        config = ExplainerConfig()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Load character
    character = load_character(character_id)

    # Override TTS backend from config if set
    effective_backend = config.tts_backend or character.tts_backend

    # 2. Generate script
    script = generate_script(topic, background, character, config, org_id=org_id)

    with tempfile.TemporaryDirectory(prefix="sable_explainer_") as tmp:
        tmp_dir = Path(tmp)

        # 3. TTS — apply phonetic corrections before synthesis
        tts_engine = create_tts_engine(effective_backend, character)

        # Merge character-level + topic-level phonetic corrections
        corrections = dict(character.phonetic_corrections)
        if background:
            corrections.update(parse_phonetic_corrections(background))

        original_script_text = script.full_text
        tts_text = apply_phonetic_corrections(original_script_text, corrections) if corrections else original_script_text

        tts_result = tts_engine.synthesize(tts_text, character, str(tmp_dir), original_text=original_script_text, org_id=org_id)

        # Resolve background video now that we know audio duration and have a tmp dir
        bg_video = _resolve_bg_video(config.background_video_path, tts_result.duration_s, tmp_dir)

        # 4. Subtitles
        ass_path = tmp_dir / "subtitles.ass"
        generate_karaoke_ass(
            tts_result.word_timestamps,
            ass_path,
            width=config.output_width,
            height=config.output_height,
        )

        # 4b. Talking head (if character has mouth images and not disabled)
        talking_head_result: Optional[TalkingHeadResult] = None
        if (
            config.talking_head_enabled
            and character.image_open_mouth
            and character.image_closed_mouth
        ):
            th_output = tmp_dir / "talking_head"  # .txt suffix added by generate_talking_head
            talking_head_result = generate_talking_head(
                mouth_open=Path(character.image_open_mouth).expanduser(),
                mouth_closed=Path(character.image_closed_mouth).expanduser(),
                word_timestamps=tts_result.word_timestamps,
                duration_s=tts_result.duration_s,
                output_path=th_output,
                fps=config.fps,
                scale=config.talking_head_scale,
            )

        # 5. FFmpeg assembly
        _assemble_video(
            bg_video=bg_video,
            audio_path=tts_result.audio_path,
            ass_path=str(ass_path),
            output_path=output_path,
            duration_s=tts_result.duration_s,
            config=config,
            talking_head_result=talking_head_result,
        )

    # 6. Generate thumbnail — randomly pick method if both are available
    from sable.character_explainer.thumbnail import (
        generate_character_thumbnail,
        generate_photo_thumbnail,
    )

    thumb_paths: dict[str, str] = {}

    has_char = bool(
        character.image_open_mouth
        and Path(character.image_open_mouth).expanduser().exists()
    )
    has_photo = bool(
        character.thumbnail_photo_path
        and Path(character.thumbnail_photo_path).expanduser().exists()
    )

    use_char = has_char
    use_photo = has_photo
    if has_char and has_photo:
        use_char = random.random() < 0.5
        use_photo = not use_char

    if use_char:
        thumb1 = output_path.with_suffix(".thumbnail.png")
        try:
            generate_character_thumbnail(character, topic, thumb1)
            thumb_paths["thumbnail"] = str(thumb1)
        except Exception as e:
            print(f"[thumbnail] character thumbnail failed: {e}")
    elif use_photo:
        assert character.thumbnail_photo_path is not None
        photo = Path(character.thumbnail_photo_path).expanduser()
        thumb2 = output_path.with_suffix(".thumbnail.png")
        try:
            generate_photo_thumbnail(photo, topic, thumb2)
            thumb_paths["thumbnail"] = str(thumb2)
        except Exception as e:
            print(f"[thumbnail] photo thumbnail failed: {e}")

    # 7. Write metadata JSON
    meta_path = output_path.parent / (output_path.name + "_meta.json")
    from datetime import datetime, timezone
    meta = {
        "id": f"exp-{output_path.stem}",
        "type": "explainer",
        "source_tool": "sable-character-explainer",
        "topic": topic,
        "character_id": character_id,
        "character_name": character.display_name,
        "script": script.full_text,
        "tts_text": tts_text,
        "word_count": script.word_count,
        "estimated_duration_s": script.estimated_duration_s,
        "tts_backend": effective_backend,
        "output": str(output_path),
        "assembled_at": datetime.now(timezone.utc).isoformat(),
        **thumb_paths,
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    return output_path


def _resolve_bg_video(path: str, duration_s: float, tmp_dir: Path) -> str:
    """Return background video path, randomly selected and trimmed to duration_s."""
    if path and Path(path).exists():
        chosen = Path(path)
    else:
        brainrot = brainrot_dir()
        candidates = [
            f for f in brainrot.iterdir()
            if f.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
        ]
        if not candidates:
            raise FileNotFoundError(
                "No background video provided and no videos found in ~/.sable/brainrot/. "
                "Pass --bg-video or add brainrot footage to ~/.sable/brainrot/."
            )
        chosen = random.choice(candidates)

    video_duration = get_duration(chosen)
    if video_duration > duration_s:
        max_start = video_duration - duration_s
        start = random.uniform(0, max_start)
        tmp_clip = tmp_dir / f"bg_clip{chosen.suffix}"
        extract_clip(chosen, tmp_clip, start, start + duration_s)
        return str(tmp_clip)

    return str(chosen)


def _assemble_video(
    bg_video: str,
    audio_path: str,
    ass_path: str,
    output_path: Path,
    duration_s: float,
    config: ExplainerConfig,
    talking_head_result: Optional[TalkingHeadResult] = None,
) -> None:
    """Merge background video + TTS audio + ASS subtitles via FFmpeg."""
    ffmpeg = require_ffmpeg()
    w, h = config.output_width, config.output_height

    # Escape ass path for FFmpeg filter (backslash/colon issues on some platforms)
    safe_ass = ass_path.replace("\\", "/").replace(":", "\\:")

    encode_flags = [
        "-c:v", "libx264", "-crf", str(config.crf), "-preset", config.video_preset,
        "-c:a", "aac", "-b:a", config.audio_bitrate,
    ]

    if talking_head_result is None:
        cmd = [
            ffmpeg, "-y",
            "-stream_loop", "-1", "-i", bg_video,
            "-i", audio_path,
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={config.fps},ass={safe_ass}",
            "-map", "0:v",
            "-map", "1:a",
            *encode_flags,
            "-t", str(duration_s),
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]
    else:
        # Feed original PNGs directly via concat demuxer — alpha channel preserved,
        # no colorkey or intermediate encode needed.
        th_scale = config.talking_head_scale
        filter_complex = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},fps={config.fps},ass={safe_ass}[bg];"
            f"[2:v]fps={config.fps},scale={th_scale}:-1:flags=lanczos,format=rgba[th];"
            f"[bg][th]overlay=x=20:y=H-h-160:shortest=1[out]"
        )
        cmd = [
            ffmpeg, "-y",
            "-stream_loop", "-1", "-i", bg_video,
            "-i", audio_path,
            # Input 2: PNG concat — decoded as RGBA, alpha goes straight to overlay
            # Note: no -r here; duration entries in the concat file control timing
            "-f", "concat", "-safe", "0", "-i", str(talking_head_result.concat_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "1:a",
            *encode_flags,
            "-t", str(duration_s),
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg assembly failed:\n{result.stderr}"
        )
