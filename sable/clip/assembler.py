"""FFmpeg assembly of stacked 9:16 clips with brainrot and captions."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, cast

from sable.shared.ffmpeg import extract_clip, stack_videos, encode_clip_only, require_ffmpeg
from sable.shared.files import atomic_write
from sable.clip.brainrot import pick as pick_brainrot, loop_to_duration
from sable.clip.captions import generate_word_captions
from sable.clip.thumbnail import generate_thumbnail

PLATFORM_PROFILES = {
    "twitter":  {"width": 720,  "half_height": 640,  "crf": 26, "preset": "fast", "audio_bitrate": "128k", "video_maxrate": None},
    "discord":  {"width": 720,  "half_height": 640,  "crf": 28, "preset": "fast", "audio_bitrate": "128k", "video_maxrate": "4M"},
    "telegram": {"width": 1080, "half_height": 960,  "crf": 23, "preset": "fast", "audio_bitrate": "192k", "video_maxrate": None},
}

_DISCORD_SIZE_WARN_BYTES = 23 * 1024 * 1024


def _auto_caption_color(source_video: Path, sample_time: float) -> str:
    """Sample a frame at sample_time and return 'yellow' or 'black' based on brightness."""
    try:
        from PIL import Image
        import io

        ffmpeg = require_ffmpeg()
        result = subprocess.run(
            [
                ffmpeg, "-ss", str(sample_time), "-i", str(source_video),
                "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-",
            ],
            capture_output=True, check=True,
        )
        img = Image.open(io.BytesIO(result.stdout)).convert("L")
        w, h = img.size
        cx, cy = w // 2, h // 2
        region = img.crop((cx - w // 4, cy - h // 4, cx + w // 4, cy + h // 4))
        import statistics
        brightness = statistics.mean(region.getdata())
        return "black" if brightness >= 128 else "yellow"
    except Exception:
        return "yellow"


def assemble_clip(
    source_video: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    account_handle: str,
    brainrot_energy: str = "medium",
    caption_style: str = "word",
    captions_segments: Optional[list[dict]] = None,
    image_overlay_path: Optional[str | Path] = None,
    caption_color: Optional[str] = None,
    caption_hint: Optional[str] = None,
    dry_run: bool = False,
    platform: str = "twitter",
    highlight_active: bool = True,
    audio_only: bool = False,
    face_track: bool = False,
    org_id: str | None = None,
    theme_tags: list[str] | None = None,
) -> dict:
    """
    Full assembly pipeline:
    1. Extract clip segment from source
    2. Pick + loop brainrot video
    3a. (clip-only) Scale source to full 9:16 — skips steps 2 & 4 brainrot path
    3. Generate ASS captions
    4. Stack + burn captions via FFmpeg

    Returns dict with output path and metadata.
    """
    source_video = Path(source_video)
    output_path = Path(output_path)
    clip_duration = end - start

    # Resolve caption color (auto-detect if not specified)
    if caption_color is None:
        if audio_only:
            # Source is a screen-share — brainrot fills the frame, not the source.
            # Auto-detecting from the source would return "black" (bright background).
            resolved_color = "yellow"
        else:
            sample_time = start + clip_duration / 2
            resolved_color = _auto_caption_color(source_video, sample_time)
    else:
        resolved_color = caption_color

    profile = PLATFORM_PROFILES.get(platform, PLATFORM_PROFILES["twitter"])

    meta = {
        "source": str(source_video),
        "output": str(output_path),
        "start": start,
        "end": end,
        "duration": clip_duration,
        "account": account_handle,
        "brainrot_energy": brainrot_energy,
        "caption_style": caption_style,
        "caption_color": resolved_color,
        "image_overlay_path": str(image_overlay_path) if image_overlay_path else None,
        "platform": platform,
        "dry_run": dry_run,
        "highlight_active": highlight_active,
        "audio_only": audio_only,
        "face_track": face_track,
        "caption": caption_hint or "",
        "theme_tags": theme_tags or [],
    }

    if dry_run:
        return meta

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # 1. Extract source clip
        source_clip = tmp_path / "source_clip.mp4"
        extract_clip(source_video, source_clip, start, end)

        # 1b. Compute face/motion crop offset if requested
        crop_x_offset = 0.0
        if face_track and not audio_only:
            from sable.clip.face_track import compute_face_offset
            crop_x_offset = compute_face_offset(
                source_clip,
                target_width=cast(int, profile["width"]),
            )
            meta["crop_x_offset"] = crop_x_offset

        # 2. Get brainrot (skipped when brainrot_energy == "none")
        clip_only = brainrot_energy == "none"
        brainrot_src = None
        if not clip_only:
            brainrot_src = pick_brainrot(energy=brainrot_energy, min_duration=5.0,
                                         tags=theme_tags or None, clip_duration=clip_duration)
            if brainrot_src is None:
                raise RuntimeError(
                    "No brainrot videos found in library. "
                    "Add some with: sable clip brainrot add <video> --energy medium"
                )
            meta["brainrot_source"] = brainrot_src
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
                generate_word_captions(adjusted, subtitle_path, style=caption_style, color=resolved_color,
                                       highlight_active=highlight_active,
                                       position="bottom" if (clip_only or audio_only) else "center")

        # 4. Stack/encode
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if audio_only and not clip_only:
            from sable.shared.ffmpeg import encode_audio_over_brainrot
            encode_audio_over_brainrot(
                source_clip=str(source_clip),
                brainrot_clip=str(brainrot_looped),
                output_path=str(output_path),
                subtitle_path=subtitle_path,
                image_overlay_path=image_overlay_path,
                platform=platform,
            )
        elif clip_only:
            encode_clip_only(
                source_clip, output_path,
                subtitle_path=subtitle_path,
                image_overlay_path=image_overlay_path,
                profile=profile,
                crop_x_offset=crop_x_offset,
            )
        else:
            stack_videos(
                source_clip, brainrot_looped, output_path,
                subtitle_path=subtitle_path,
                image_overlay_path=image_overlay_path,
                profile=profile,
                crop_x_offset=crop_x_offset,
            )

    # Generate thumbnail
    thumb_path = output_path.with_suffix(".thumbnail.png")
    generate_thumbnail(
        headline_hint=str(meta.get("caption") or "")[:200],
        output_path=thumb_path,
        source_video=source_video,
        clip_start=start,
        clip_end=end,
        org_id=org_id,
    )
    meta["thumbnail"] = str(thumb_path)

    # Discord file-size warning
    if platform == "discord" and output_path.stat().st_size > _DISCORD_SIZE_WARN_BYTES:
        print(
            "\033[33mWarning: clip exceeds 23 MB — may hit Discord's 25 MB free-tier limit. "
            "Consider keeping --platform discord clips under 30 s.\033[0m",
            file=sys.stderr,
        )

    # Write sidecar metadata so bad brainrot can be traced later
    meta["assembled_at"] = datetime.now(timezone.utc).isoformat()
    meta_path = output_path.with_suffix(".meta.json")
    atomic_write(meta_path, json.dumps(meta, indent=2))

    return meta
