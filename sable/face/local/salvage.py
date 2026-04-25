"""Salvage a crashed roop run.

Roop's frame_enhancer (GFPGAN) intermittently crashes mid-stream under memory
pressure (cv2.imread returns None — see FACE_SWAP_LESSONS.md bug #5). When this
happens, the temp PNG dir already contains the swapper output and a partial
enhancer pass.

This helper:
  1. Identifies which temp PNGs were not yet enhanced (mtime older than the
     start of the enhancer pass).
  2. Re-runs face_enhancer on just those frames using a retry-wrapped imread.
  3. Reassembles the video at CRF 12 and restores the source audio.

Reference recipe: see ~/Desktop/fletcher_extract/finish_enhance.py.
Assumes a working roop install at ~/roop-env/roop (overridable via
`face_local.roop_path` config or SABLE_ROOP_PATH env var).
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sable.face.local import config as fl_cfg
from sable.face.local.common import imread_retry


@dataclass
class SalvageParams:
    fps: int = 30
    crf: int = 12
    preset: str = "medium"
    pix_fmt: str = "yuv420p"


def finish_enhance(
    temp_dir: Path,
    target_video: Path,
    output_video: Path,
    frame_names: list[str],
    params: Optional[SalvageParams] = None,
    *,
    roop_override: Optional[Path | str] = None,
    progress=print,
) -> dict:
    """Run face_enhancer on `frame_names` (PNG basenames inside `temp_dir`),
    then reassemble + restore audio.

    Returns metadata dict.
    """
    p = params or SalvageParams()
    roop_dir = fl_cfg.roop_path(roop_override)
    if not roop_dir.is_dir():
        raise FileNotFoundError(
            f"Roop install not found at {roop_dir}. "
            "Set face_local.roop_path or SABLE_ROOP_PATH."
        )

    # Lazy import — roop must be on sys.path
    sys.path.insert(0, str(roop_dir))
    try:
        import roop.globals  # type: ignore
        roop.globals.execution_providers = ["CoreMLExecutionProvider"]
        roop.globals.execution_threads = 1
        from roop.processors.frame import face_enhancer  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"Failed to import roop from {roop_dir}: {e}")

    import cv2

    paths = [temp_dir / f"{n}.png" if not n.endswith(".png") else temp_dir / n for n in frame_names]
    progress(f"Enhancing {len(paths)} remaining frames...")

    t0 = time.time()
    for i, fp in enumerate(paths, 1):
        img = imread_retry(fp, attempts=3, sleep_s=0.5)
        if img is None:
            raise RuntimeError(f"FATAL: could not read {fp} after retries")
        result = face_enhancer.process_frame(None, None, img)
        cv2.imwrite(str(fp), result)
        if i % 10 == 0 or i == len(paths):
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (len(paths) - i) / rate if rate > 0 else 0
            progress(f"  {i}/{len(paths)}  ({rate:.2f} f/s, ETA {eta:.0f}s)")

    progress(f"\nEnhancement done in {time.time() - t0:.0f}s. Assembling video...")

    temp_video = temp_dir / "temp.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-r", str(p.fps), "-i", str(temp_dir / "%04d.png"),
            "-c:v", "libx264", "-crf", str(p.crf), "-preset", p.preset,
            "-pix_fmt", p.pix_fmt, str(temp_video),
        ],
        check=True,
    )
    progress(f"  encoded -> {temp_video}")

    output_video = Path(output_video)
    output_video.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(temp_video), "-i", str(target_video),
            "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0?", str(output_video),
        ],
        check=True,
    )
    progress(f"  restored audio -> {output_video}")

    return {
        "output": str(output_video),
        "frames_enhanced": len(paths),
        "elapsed_s": round(time.time() - t0, 1),
    }
