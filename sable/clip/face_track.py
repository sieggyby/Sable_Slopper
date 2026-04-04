"""Face-centered crop offset computation for clip assembly.

Samples frames from a video, detects faces, and returns a fractional
horizontal crop offset that centers the dominant face region. Falls back
to center-crop (0.0) when no faces are found or face_recognition is
unavailable.

CLIP-3 adds motion-based fallback via optical flow when no faces are detected.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from sable.shared.ffmpeg import get_video_dimensions, get_duration, require_ffmpeg

logger = logging.getLogger(__name__)


def compute_face_offset(
    video_path: str | Path,
    target_width: int,
    sample_count: int = 6,
) -> float:
    """Compute a fractional horizontal offset to center the dominant face region.

    Args:
        video_path: Path to the source video file.
        target_width: Width of the output crop (e.g. 720 or 1080).
        sample_count: Number of frames to sample across the clip.

    Returns:
        Fractional offset in [-1.0, 1.0] where 0 = center crop.
        -1.0 = crop at left edge, +1.0 = crop at right edge.
        Applied by ffmpeg as: crop_x = (in_w - target_w)/2 + offset * (in_w - target_w)/2
    """
    try:
        import face_recognition
        import numpy as np
        from PIL import Image
    except ImportError:
        logger.debug("face_recognition not available — using center crop")
        return 0.0

    video_path = Path(video_path)
    if not video_path.exists():
        return 0.0

    # Get source dimensions
    try:
        src_w, src_h = get_video_dimensions(video_path)
    except (ValueError, RuntimeError):
        return 0.0

    if src_w <= target_width:
        return 0.0

    # Extract sample frames, process, and clean up
    tmp_dir_obj = tempfile.TemporaryDirectory(prefix="sable_face_")
    tmp_dir = Path(tmp_dir_obj.name)
    try:
        frames = _extract_sample_frames(video_path, sample_count, tmp_dir)
        if not frames:
            return _compute_motion_offset(video_path, src_w, target_width)

        # Detect faces in each frame and collect x-centers
        face_x_centers: list[float] = []
        face_weights: list[float] = []

        for frame_path in frames:
            try:
                arr = np.array(Image.open(frame_path).convert("RGB"))
                locs = face_recognition.face_locations(arr, model="hog")
                if not locs:
                    continue
                best_loc = max(locs, key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]))
                top, right, bottom, left = best_loc
                x_center = (left + right) / 2.0
                area = abs((right - left) * (bottom - top))
                face_x_centers.append(x_center)
                face_weights.append(area)
            except Exception:
                continue
    finally:
        tmp_dir_obj.cleanup()

    if not face_x_centers:
        logger.debug("No faces detected in %d sampled frames", len(frames))
        return _compute_motion_offset(video_path, src_w, target_width)

    # Weighted average of face x-centers (in source pixel coordinates)
    total_weight = sum(face_weights)
    avg_x = sum(x * w for x, w in zip(face_x_centers, face_weights)) / total_weight

    # Convert to fractional offset [-1, 1]
    # Center of frame = src_w / 2.  Max pan room = (src_w - target_width) / 2
    pan_room = (src_w - target_width) / 2.0
    offset_px = avg_x - src_w / 2.0
    fraction = max(-1.0, min(1.0, offset_px / pan_room)) if pan_room > 0 else 0.0

    logger.debug(
        "Face offset: avg_x=%.0f, fraction=%.3f (from %d detections)",
        avg_x, fraction, len(face_x_centers),
    )
    return fraction


def _compute_motion_offset(
    video_path: str | Path,
    src_width: int,
    target_width: int,
) -> float:
    """CLIP-3: Optical flow fallback — compute pan offset from motion center.

    Samples frames at ~1fps, computes dense optical flow, and finds the
    horizontal center of motion. Returns fractional offset [-1.0, 1.0].

    Returns 0.0 if cv2 is unavailable or motion is too uniform.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.debug("cv2 not available — using center crop")
        return 0.0

    video_path = Path(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0.0

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_skip = max(1, int(fps))
    max_samples = 15

    prev_gray = None
    motion_x_centers: list[float] = []
    motion_magnitudes: list[float] = []
    frame_idx = 0
    samples = 0

    while samples < max_samples:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_skip != 0:
            frame_idx += 1
            continue
        frame_idx += 1
        samples += 1

        h, w = frame.shape[:2]
        scale = min(1.0, 480.0 / w)
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is None:
            prev_gray = gray
            continue

        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, gray, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
        )
        prev_gray = gray

        mag = np.sqrt(flow[:, :, 0] ** 2 + flow[:, :, 1] ** 2)
        col_mag = mag.mean(axis=0)
        total_mag = col_mag.sum()

        if total_mag < 1e-6:
            continue

        col_indices = np.arange(len(col_mag), dtype=np.float64)
        x_center = (col_indices * col_mag).sum() / total_mag
        x_center_orig = x_center / scale

        motion_x_centers.append(x_center_orig)
        motion_magnitudes.append(total_mag)

    cap.release()

    if not motion_x_centers:
        return 0.0

    total_w = sum(motion_magnitudes)
    avg_x = sum(x * m for x, m in zip(motion_x_centers, motion_magnitudes)) / total_w

    # Convert to fractional offset
    pan_room = (src_width - target_width) / 2.0
    offset_px = avg_x - src_width / 2.0
    fraction = max(-1.0, min(1.0, offset_px / pan_room)) if pan_room > 0 else 0.0

    logger.debug(
        "Motion offset: avg_x=%.0f, fraction=%.3f (from %d flow samples)",
        avg_x, fraction, len(motion_x_centers),
    )
    return fraction


def _extract_sample_frames(video_path: Path, count: int, tmp_dir: Path) -> list[Path]:
    """Extract evenly-spaced frames from a video for face detection."""
    try:
        duration = get_duration(video_path)
    except Exception:
        return []

    if duration <= 0:
        return []

    ffmpeg = require_ffmpeg()

    margin = min(0.5, duration * 0.05)
    step = (duration - 2 * margin) / max(count - 1, 1)
    timestamps = [margin + i * step for i in range(count)]

    frames: list[Path] = []
    for i, ts in enumerate(timestamps):
        out = tmp_dir / f"frame_{i:03d}.png"
        try:
            subprocess.run(
                [ffmpeg, "-ss", str(ts), "-i", str(video_path),
                 "-frames:v", "1", "-f", "image2", str(out)],
                capture_output=True, check=True,
            )
            if out.exists():
                frames.append(out)
        except subprocess.CalledProcessError:
            continue

    return frames
