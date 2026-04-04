"""FFmpeg subprocess wrapper with actionable error messages."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

_FFMPEG_SPECIAL = re.compile(r'[;:\[\]=]')


def _validate_subtitle_path(path) -> None:
    if _FFMPEG_SPECIAL.search(str(path)):
        from sable.platform.errors import SableError, INVALID_PATH
        raise SableError(INVALID_PATH, f"Subtitle path has FFmpeg special chars: {path!r}")


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise RuntimeError(
            "ffmpeg not found. Install it: brew install ffmpeg  (macOS) or apt install ffmpeg"
        )
    return path


def require_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if path is None:
        raise RuntimeError("ffprobe not found. Install ffmpeg (includes ffprobe).")
    return path


def run(args: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run an ffmpeg command. Raises RuntimeError with actionable message on failure."""
    try:
        result = subprocess.run(
            args,
            check=check,
            capture_output=capture,
            text=True,
        )
        return result
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        msg = _parse_ffmpeg_error(stderr)
        raise RuntimeError(f"FFmpeg failed: {msg}\n\nFull stderr:\n{stderr}") from None
    except FileNotFoundError:
        raise RuntimeError(f"Command not found: {args[0]}. Is ffmpeg installed?")


def _parse_ffmpeg_error(stderr: str) -> str:
    """Extract the most useful line from ffmpeg stderr."""
    for line in reversed(stderr.splitlines()):
        line = line.strip()
        if line and not line.startswith("frame=") and not line.startswith("size="):
            return line
    return "Unknown error"


def probe(path: str | Path) -> dict:
    """Run ffprobe and return JSON metadata."""
    ffprobe = require_ffprobe()
    result = subprocess.run(
        [
            ffprobe, "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def get_duration(path: str | Path) -> float:
    """Return duration in seconds."""
    info = probe(path)
    return float(info["format"].get("duration", 0))


def get_video_dimensions(path: str | Path) -> tuple[int, int]:
    """Return (width, height) of first video stream."""
    info = probe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    raise ValueError(f"No video stream found in {path}")


def extract_audio(input_path: str | Path, output_path: str | Path) -> None:
    """Extract audio to WAV."""
    run([
        require_ffmpeg(), "-y", "-i", str(input_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(output_path),
    ], capture=True)


def extract_clip(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
) -> None:
    """Extract a time range from a video file."""
    duration = end - start
    run([
        require_ffmpeg(), "-y",
        "-ss", str(start), "-i", str(input_path),
        "-t", str(duration),
        "-c", "copy",
        str(output_path),
    ], capture=True)


def stack_videos(
    top_path: str | Path,
    bottom_path: str | Path,
    output_path: str | Path,
    subtitle_path: Optional[str | Path] = None,
    image_overlay_path: Optional[str | Path] = None,
    profile: Optional[dict] = None,
    interview_audio_vol: float = 1.0,
    brainrot_audio_vol: float = 0.0,
    crop_x_offset: float = 0.0,
) -> None:
    """
    Stack two videos vertically into a 9:16 portrait layout.
    Top = brainrot (input 1), Bottom = source/interview (input 0).
    Audio: interview (input 0) through loudnorm; brainrot audio silent by default.
    Profile controls resolution and encoding (defaults to 1080x1920, CRF 23, 192k).

    crop_x_offset: fractional pan offset [-1.0, 1.0] applied to source (bottom).
    0 = center crop, -1 = left edge, +1 = right edge.
    """
    p = profile or {
        "width": 1080, "half_height": 960,
        "crf": 23, "preset": "fast",
        "audio_bitrate": "192k", "video_maxrate": None,
    }
    w, hh = p["width"], p["half_height"]

    ffmpeg = require_ffmpeg()
    # Fractional offset applied at crop time using in_w (post-scale dimensions).
    # crop_x = (in_w - w)/2 + offset * (in_w - w)/2 = (in_w - w)/2 * (1 + offset)
    if crop_x_offset:
        factor = 1.0 + crop_x_offset
        bottom_crop = f"crop={w}:{hh}:trunc((in_w-{w})/2*{factor:.4f}):(in_h-{hh})/2"
    else:
        bottom_crop = f"crop={w}:{hh}"
    filter_graph = (
        f"[1:v]setpts=PTS-STARTPTS,fps=30,scale={w}:{hh}:force_original_aspect_ratio=increase,"
        f"crop={w}:{hh}[top];"
        f"[0:v]setpts=PTS-STARTPTS,fps=30,scale={w}:{hh}:force_original_aspect_ratio=increase,"
        f"{bottom_crop}[bottom];"
        "[top][bottom]vstack=inputs=2[stacked]"
    )

    inputs = ["-i", str(top_path), "-i", str(bottom_path)]

    # Audio: interview (input 0) loud + normalized; brainrot (input 1) optionally mixed
    if brainrot_audio_vol > 0:
        audio_filter = (
            "[0:a]asetpts=PTS-STARTPTS,dynaudnorm=f=150:g=15[interview_norm];"
            f"[1:a]volume={brainrot_audio_vol}[ambient];"
            "[interview_norm][ambient]amix=inputs=2:normalize=0[audio_out]"
        )
    else:
        audio_filter = "[0:a]asetpts=PTS-STARTPTS,dynaudnorm=f=150:g=15[audio_out]"
    filter_graph += f";{audio_filter}"

    current = "[stacked]"

    if image_overlay_path:
        inputs += ["-i", str(image_overlay_path)]
        img_stream = f"[{len(inputs) // 2 - 1}:v]"
        filter_graph += (
            f";{img_stream}scale=200:-1[img];"
            f"{current}[img]overlay=x=20:y=H-h-20[overlaid]"
        )
        current = "[overlaid]"

    if subtitle_path:
        _validate_subtitle_path(subtitle_path)
        filter_graph += f";{current}ass={subtitle_path}[out]"
        output_map = "[out]"
    else:
        output_map = current

    encode_flags = [
        "-c:v", "libx264", "-preset", p["preset"], "-crf", str(p["crf"]),
        "-c:a", "aac", "-b:a", p["audio_bitrate"],
    ]
    if p.get("video_maxrate"):
        encode_flags += ["-maxrate", p["video_maxrate"], "-bufsize", _double_rate(p["video_maxrate"])]

    run([
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", output_map,
        "-map", "[audio_out]",
        "-shortest",
        *encode_flags,
        str(output_path),
    ], capture=True)


def encode_clip_only(
    source_path: str | Path,
    output_path: str | Path,
    subtitle_path: Optional[str | Path] = None,
    image_overlay_path: Optional[str | Path] = None,
    profile: Optional[dict] = None,
    crop_x_offset: float = 0.0,
) -> None:
    """
    Encode source clip to full 9:16 portrait (no brainrot split).
    Source is scaled and cropped to fill the entire frame.
    Audio: source through dynaudnorm. Captions and image overlay optional.

    crop_x_offset: fractional pan offset [-1.0, 1.0]. 0 = center.
    """
    p = profile or {
        "width": 1080, "half_height": 960,
        "crf": 23, "preset": "fast",
        "audio_bitrate": "192k", "video_maxrate": None,
    }
    w, full_h = p["width"], p["half_height"] * 2

    ffmpeg = require_ffmpeg()
    if crop_x_offset:
        factor = 1.0 + crop_x_offset
        crop_expr = f"crop={w}:{full_h}:trunc((in_w-{w})/2*{factor:.4f}):(in_h-{full_h})/2"
    else:
        crop_expr = f"crop={w}:{full_h}"
    filter_graph = (
        f"[0:v]setpts=PTS-STARTPTS,fps=30,scale={w}:{full_h}:force_original_aspect_ratio=increase,"
        f"{crop_expr}[scaled]"
    )
    filter_graph += ";[0:a]asetpts=PTS-STARTPTS,dynaudnorm=f=150:g=15[audio_out]"

    inputs = ["-i", str(source_path)]
    current = "[scaled]"

    if image_overlay_path:
        inputs += ["-i", str(image_overlay_path)]
        img_stream = f"[{len(inputs) // 2 - 1}:v]"
        filter_graph += (
            f";{img_stream}scale=200:-1[img];"
            f"{current}[img]overlay=x=20:y=H-h-20[overlaid]"
        )
        current = "[overlaid]"

    if subtitle_path:
        _validate_subtitle_path(subtitle_path)
        filter_graph += f";{current}ass={subtitle_path}[out]"
        output_map = "[out]"
    else:
        output_map = current

    encode_flags = [
        "-c:v", "libx264", "-preset", p["preset"], "-crf", str(p["crf"]),
        "-c:a", "aac", "-b:a", p["audio_bitrate"],
    ]
    if p.get("video_maxrate"):
        encode_flags += ["-maxrate", p["video_maxrate"], "-bufsize", _double_rate(p["video_maxrate"])]

    run([
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", output_map,
        "-map", "[audio_out]",
        *encode_flags,
        str(output_path),
    ], capture=True)


def encode_audio_over_brainrot(
    source_clip: str,
    brainrot_clip: str,
    output_path: str,
    subtitle_path: Optional[str | Path] = None,
    image_overlay_path: Optional[str | Path] = None,
    platform: str = "twitter",
) -> None:
    """
    Audio-only mode: brainrot fills full 9:16 frame; source contributes audio only.
    Use for podcasts and screen-share recordings with no usable video content.
    """
    from sable.clip.assembler import PLATFORM_PROFILES
    p: dict[str, Any] = PLATFORM_PROFILES.get(platform, PLATFORM_PROFILES["twitter"])
    w = p["width"]
    full_h = p["half_height"] * 2

    ffmpeg = require_ffmpeg()
    filter_graph = (
        f"[0:v]setpts=PTS-STARTPTS,fps=30,scale={w}:{full_h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{full_h}[bg]"
    )
    filter_graph += ";[1:a]asetpts=PTS-STARTPTS,dynaudnorm=f=150:g=15[audio_out]"

    inputs = ["-i", str(brainrot_clip), "-i", str(source_clip)]
    current = "[bg]"

    if image_overlay_path:
        inputs += ["-i", str(image_overlay_path)]
        img_stream = f"[{len(inputs) // 2 - 1}:v]"
        filter_graph += (
            f";{img_stream}scale=200:-1[img];"
            f"{current}[img]overlay=x=20:y=H-h-20[overlaid]"
        )
        current = "[overlaid]"

    if subtitle_path:
        _validate_subtitle_path(subtitle_path)
        filter_graph += f";{current}ass={subtitle_path}[out]"
        output_map = "[out]"
    else:
        output_map = current

    encode_flags = [
        "-c:v", "libx264", "-preset", p["preset"], "-crf", str(p["crf"]),
        "-c:a", "aac", "-b:a", p["audio_bitrate"],
    ]
    if p.get("video_maxrate"):
        encode_flags += ["-maxrate", p["video_maxrate"], "-bufsize", _double_rate(p["video_maxrate"])]

    run([
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", output_map,
        "-map", "[audio_out]",
        "-shortest",
        *encode_flags,
        str(output_path),
    ], capture=True)


def _double_rate(rate: str) -> str:
    """Double a bitrate string like '4M' → '8M' for bufsize."""
    if rate.endswith("M"):
        return f"{int(rate[:-1]) * 2}M"
    if rate.endswith("k"):
        return f"{int(rate[:-1]) * 2}k"
    return str(int(rate) * 2)


def overlay_image_on_video(
    video_path: str | Path,
    image_path: str | Path,
    output_path: str | Path,
    position: str = "bottom-left",
    padding: int = 20,
    scale: int = 200,
) -> None:
    """Overlay a PNG image onto a video. Default position: bottom-left."""
    ffmpeg = require_ffmpeg()

    x: Any
    y: Any
    if position == "bottom-left":
        x, y = padding, f"H-h-{padding}"
    elif position == "bottom-right":
        x, y = f"W-w-{padding}", f"H-h-{padding}"
    elif position == "top-left":
        x, y = padding, padding
    elif position == "top-right":
        x, y = f"W-w-{padding}", padding
    else:
        x, y = padding, f"H-h-{padding}"

    filter_graph = f"[1:v]scale={scale}:-1[img];[0:v][img]overlay=x={x}:y={y}[out]"

    run([
        ffmpeg, "-y",
        "-i", str(video_path),
        "-i", str(image_path),
        "-filter_complex", filter_graph,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ], capture=True)
