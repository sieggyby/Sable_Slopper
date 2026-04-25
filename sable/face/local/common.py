"""Shared helpers for the local face-swap pipeline.

Heavy imports (cv2, numpy, insightface) are kept local to functions so the
package itself stays importable on machines without the [face-local] extras.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def laplacian_var(img):
    import cv2
    return cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()


def frontality(face) -> float:
    import numpy as np
    if not hasattr(face, "pose") or face.pose is None:
        return 1.0
    pitch, yaw, _ = face.pose
    angle = float(np.sqrt(yaw**2 + pitch**2))
    return max(0.0, 1.0 - angle / 60.0)


def crop_headshot(frame, bbox, margin: float = 0.7):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [float(v) for v in bbox]
    bw, bh = x2 - x1, y2 - y1
    side = max(bw, bh)
    pad = side * margin
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    half = side / 2.0 + pad
    cx1 = int(max(0, cx - half))
    cy1 = int(max(0, cy - half))
    cx2 = int(min(w, cx + half))
    cy2 = int(min(h, cy + half))
    return frame[cy1:cy2, cx1:cx2]


def probe_resolution(video: Path) -> tuple[int, int]:
    """Return (width, height) for the first video stream."""
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0",
            str(video),
        ],
        capture_output=True, text=True, check=True,
    )
    w, h = [int(x) for x in r.stdout.strip().split("x")]
    return w, h


def make_face_analyser():
    """Build an InsightFace FaceAnalysis with sane defaults (CPU, buffalo_l)."""
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


def imread_retry(path: str | Path, attempts: int = 3, sleep_s: float = 0.5):
    """cv2.imread with retry — see FACE_SWAP_LESSONS.md bug #5."""
    import time
    import cv2
    p = str(path)
    for i in range(attempts):
        img = cv2.imread(p)
        if img is not None:
            return img
        time.sleep(sleep_s * (i + 1))
    return None


def stage1_sample(video: Path, sample_dir: Path, every_sec: float, scale_h: int) -> None:
    """Sample one frame every `every_sec` seconds, scaled to `scale_h`."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(sample_dir / "f_%05d.jpg")
    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-vf", f"fps=1/{every_sec},scale=-2:{scale_h}",
        "-q:v", "3", pattern,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def extract_full_frame(video: Path, ts_seconds: float, dest: Path) -> None:
    """Extract a single full-resolution frame at `ts_seconds`."""
    cmd = [
        "ffmpeg", "-y", "-ss", f"{ts_seconds:.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "1", str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def composite_image(images: list, weights, out_size: int = 448) -> "np.ndarray":  # noqa: F821
    """Pixel-mean composite of aligned 112x112 images (visual-only sanity check)."""
    import numpy as np
    import cv2
    if not images:
        raise ValueError("composite_image: empty list")
    stack = np.stack(images).astype(np.float32)
    w = weights[: len(images)]
    comp = (stack * w[:, None, None, None]).sum(axis=0)
    comp = np.clip(comp, 0, 255).astype(np.uint8)
    return cv2.resize(comp, (out_size, out_size), interpolation=cv2.INTER_CUBIC)
