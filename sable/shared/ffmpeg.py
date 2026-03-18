"""FFmpeg subprocess wrapper with actionable error messages."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


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
) -> None:
    """
    Stack two videos vertically into 1080x1920 (9:16).
    Top = source (960px tall), Bottom = brainrot (960px tall).
    Audio from top only.
    """
    ffmpeg = require_ffmpeg()
    filter_graph = (
        "[0:v]scale=1080:960:force_original_aspect_ratio=decrease,"
        "pad=1080:960:(ow-iw)/2:(oh-ih)/2:black[top];"
        "[1:v]scale=1080:960:force_original_aspect_ratio=increase,"
        "crop=1080:960[bottom];"
        "[top][bottom]vstack=inputs=2[stacked]"
    )

    if subtitle_path:
        filter_graph += f";[stacked]ass={subtitle_path}[out]"
        output_map = "[out]"
    else:
        output_map = "[stacked]"

    run([
        ffmpeg, "-y",
        "-i", str(top_path),
        "-i", str(bottom_path),
        "-filter_complex", filter_graph,
        "-map", output_map,
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ], capture=True)
