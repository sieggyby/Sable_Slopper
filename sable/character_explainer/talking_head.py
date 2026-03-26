"""Talking head video generator: animates mouth-open/closed images in sync with speech."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass
class TalkingHeadResult:
    concat_path: Path    # FFmpeg concat demuxer file referencing the original PNGs
    has_alpha: bool      # True when PNGs are RGBA (overlay filter uses alpha directly)


def generate_talking_head(
    mouth_open: Path,
    mouth_closed: Path,
    word_timestamps: list[dict],   # [{"start": 0.1, "end": 0.5, "text": "word"}]
    duration_s: float,
    output_path: Path,             # concat.txt will be written here (suffix ignored)
    fps: int = 30,
    scale: int = 320,              # unused here; consumed by _assemble_video
) -> TalkingHeadResult:
    """
    Build timing metadata for the talking head animation.

    No intermediate video is encoded. The original PNG files (with their alpha
    channels intact) are referenced directly in a concat demuxer file. FFmpeg
    reads them at assembly time and the overlay filter uses the RGBA alpha
    channel natively — no colorkey or background compositing needed.
    """
    has_alpha = _check_has_alpha(mouth_open) or _check_has_alpha(mouth_closed)
    segments = _build_segments(word_timestamps, duration_s, fps, mouth_open, mouth_closed)

    concat_path = output_path.with_suffix(".txt")
    _write_concat_file(concat_path, segments)

    return TalkingHeadResult(concat_path=concat_path, has_alpha=has_alpha)


def _check_has_alpha(image_path: Path) -> bool:
    """Return True if the image has a non-trivial (partially transparent) alpha channel."""
    try:
        from PIL import Image

        img = Image.open(image_path)
        if img.mode != "RGBA":
            return False
        min_alpha = cast(tuple[int, int], img.split()[3].getextrema())[0]
        return min_alpha < 255
    except Exception:
        return False


_FLUTTER_THRESHOLD = 0.153  # speech segments longer than this get a mid-word flutter
_FLUTTER_FRAMES    = 2      # frames of mouth-closed to insert mid-word


def _build_segments(
    word_timestamps: list[dict],
    duration_s: float,
    fps: int,
    mouth_open: Path,
    mouth_closed: Path,
) -> list[tuple[Path, float]]:
    """Build list of (image_path, duration_s) segments from word timestamps."""
    min_dur = 1.0 / fps
    segments: list[tuple[Path, float]] = []

    if not word_timestamps:
        return [(mouth_open, duration_s)]

    cursor = 0.0
    for word in word_timestamps:
        start = word["start"]
        end = word["end"]

        silence_dur = start - cursor
        if silence_dur >= min_dur:
            segments.append((mouth_closed, silence_dur))

        speak_dur = end - start
        if speak_dur >= min_dur:
            if speak_dur > _FLUTTER_THRESHOLD:
                first_open  = speak_dur * 0.45
                flutter_dur = _FLUTTER_FRAMES / fps
                second_open = speak_dur - first_open - flutter_dur
                if first_open >= min_dur:
                    segments.append((mouth_open, first_open))
                if flutter_dur >= min_dur:
                    segments.append((mouth_closed, flutter_dur))
                if second_open >= min_dur:
                    segments.append((mouth_open, second_open))
            else:
                segments.append((mouth_open, speak_dur))

        cursor = end

    trailing = duration_s - cursor
    if trailing >= min_dur:
        segments.append((mouth_closed, trailing))

    return segments


def _write_concat_file(concat_file: Path, segments: list[tuple[Path, float]]) -> None:
    """Write FFmpeg concat demuxer file referencing original PNG paths."""
    lines = []
    for img_path, dur in segments:
        lines.append(f"file '{img_path.resolve()}'")
        lines.append(f"duration {dur:.6f}")
    # Repeat final entry (concat demuxer quirk — last frame needs a duplicate)
    if segments:
        lines.append(f"file '{segments[-1][0].resolve()}'")
    concat_file.write_text("\n".join(lines) + "\n")
