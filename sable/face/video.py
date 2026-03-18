"""Frame extraction, parallel face swap, video reassembly."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from sable.shared.ffmpeg import run as ffmpeg_run, require_ffmpeg, get_duration
from sable.face.swapper import swap_image
from sable.face.optimize import filter_frames_with_faces, dedup_frames
from sable.face.safety import log_swap


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    fps: float = 30.0,
) -> list[Path]:
    """Extract frames as PNG files. Returns sorted list of frame paths."""
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_run([
        require_ffmpeg(), "-y",
        "-i", str(video_path),
        "-vf", f"fps={fps}",
        str(output_dir / "frame_%06d.png"),
    ], capture=True)

    return sorted(output_dir.glob("frame_*.png"))


def reassemble_video(
    frames_dir: str | Path,
    original_video: str | Path,
    output_path: str | Path,
    fps: float = 30.0,
) -> None:
    """Reassemble frames back into a video with original audio."""
    frames_dir = Path(frames_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg_run([
        require_ffmpeg(), "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%06d.png"),
        "-i", str(original_video),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        "-shortest",
        str(output_path),
    ], capture=True)


def swap_video(
    video_path: str | Path,
    reference_path: str | Path,
    output_path: str | Path,
    reference_name: str = "unknown",
    quality: str = "medium",
    max_workers: int = 4,
    use_face_filter: bool = True,
    use_dedup: bool = True,
) -> dict:
    """
    Full video face swap pipeline.
    quality: low (native model), medium (frame-by-frame if ≤15s else native), high (always frame-by-frame)
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    duration = get_duration(video_path)

    use_frame_by_frame = _should_use_frames(quality, duration)

    if not use_frame_by_frame:
        # Native video model (faster, lower quality)
        result_path, model_used = swap_image(
            video_path, reference_path, output_path
        )
        log_swap(reference_name, str(video_path), str(output_path), model=model_used)
        return {"output": str(output_path), "strategy": "native", "model": model_used}

    # Frame-by-frame
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        frames_dir = tmp_path / "frames"
        swapped_dir = tmp_path / "swapped"
        swapped_dir.mkdir()

        # Extract
        frames = extract_frames(video_path, frames_dir)
        total = len(frames)

        # Optional pre-filters
        if use_face_filter:
            frames = filter_frames_with_faces(frames)
        if use_dedup:
            frames = dedup_frames(frames)

        # Parallel swap
        errors = []

        def _swap_frame(frame: Path) -> Path:
            dest = swapped_dir / frame.name
            swap_image(frame, reference_path, dest)
            return dest

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_swap_frame, f): f for f in frames}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    errors.append(str(e))

        # Copy non-swapped frames as-is (fill gaps)
        all_frame_names = sorted(f.name for f in frames_dir.glob("frame_*.png"))
        swapped_names = {f.name for f in swapped_dir.glob("frame_*.png")}
        for name in all_frame_names:
            if name not in swapped_names:
                shutil.copy2(str(frames_dir / name), str(swapped_dir / name))

        # Reassemble
        reassemble_video(swapped_dir, video_path, output_path)

    log_swap(reference_name, str(video_path), str(output_path), model="frame-by-frame")

    meta = {
        "output": str(output_path),
        "strategy": "frame-by-frame",
        "total_frames": total,
        "swapped_frames": total - len(errors),
        "errors": len(errors),
    }
    return meta


def _should_use_frames(quality: str, duration: float) -> bool:
    if quality == "high":
        return True
    if quality == "low":
        return False
    # medium: frame-by-frame if ≤15s
    return duration <= 15.0
