"""FFmpeg assembly of stacked 9:16 clips with brainrot and captions."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from sable.shared.ffmpeg import extract_clip, stack_videos, get_duration
from sable.clip.brainrot import pick as pick_brainrot, loop_to_duration
from sable.clip.captions import generate_word_captions


def assemble_clip(
    source_video: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    account_handle: str,
    brainrot_energy: str = "medium",
    caption_style: str = "word",
    captions_segments: Optional[list[dict]] = None,
    dry_run: bool = False,
) -> dict:
    """
    Full assembly pipeline:
    1. Extract clip segment from source
    2. Pick + loop brainrot video
    3. Generate ASS captions
    4. Stack + burn captions via FFmpeg

    Returns dict with output path and metadata.
    """
    source_video = Path(source_video)
    output_path = Path(output_path)
    clip_duration = end - start

    meta = {
        "source": str(source_video),
        "output": str(output_path),
        "start": start,
        "end": end,
        "duration": clip_duration,
        "brainrot_energy": brainrot_energy,
        "caption_style": caption_style,
        "dry_run": dry_run,
    }

    if dry_run:
        return meta

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # 1. Extract source clip
        source_clip = tmp_path / "source_clip.mp4"
        extract_clip(source_video, source_clip, start, end)

        # 2. Get brainrot
        brainrot_src = pick_brainrot(energy=brainrot_energy, min_duration=5.0)
        if brainrot_src is None:
            raise RuntimeError(
                "No brainrot videos found in library. "
                "Add some with: sable clip brainrot add <video> --energy medium"
            )

        brainrot_looped = tmp_path / "brainrot_looped.mp4"
        loop_to_duration(brainrot_src, clip_duration, brainrot_looped)

        # 3. Captions
        subtitle_path = None
        if caption_style != "none" and captions_segments:
            # Offset timestamps to clip start
            adjusted = [
                {**s, "start": s["start"] - start, "end": s["end"] - start}
                for s in captions_segments
                if s["start"] >= start and s["end"] <= end + 0.5
            ]
            if adjusted:
                subtitle_path = tmp_path / "captions.ass"
                generate_word_captions(adjusted, subtitle_path, style=caption_style)

        # 4. Stack and encode
        output_path.parent.mkdir(parents=True, exist_ok=True)
        stack_videos(source_clip, brainrot_looped, output_path, subtitle_path=subtitle_path)

    return meta
