"""Two-stage best-face extraction.

Stage 1: ffmpeg samples one frame every N seconds at ~1080p.
         InsightFace detects/scores all faces; we keep timestamps + bboxes
         for the top-K composite-scored candidates.
Stage 2: For each top candidate, re-extract that exact timestamp from the source
         at full resolution and save a clean headshot crop.

Filenames embed the score components so picks are self-identifying.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sable.face.local.common import (
    crop_headshot,
    extract_full_frame,
    frontality,
    laplacian_var,
    make_face_analyser,
    probe_resolution,
    stage1_sample,
)


@dataclass
class ExtractParams:
    every_sec: float = 2.0
    detect_h: int = 1080
    top: int = 12
    min_face_frac: float = 0.08


def extract(
    video: Path,
    workspace: Path,
    params: Optional[ExtractParams] = None,
    *,
    progress=print,
) -> list[Path]:
    """Run both stages. Returns the list of saved headshot paths."""
    import cv2

    p = params or ExtractParams()
    samples_dir = workspace / "samples"
    headshots_dir = workspace / "headshots"
    headshots_dir.mkdir(parents=True, exist_ok=True)

    if not glob.glob(str(samples_dir / "f_*.jpg")):
        progress(f"[stage1] sampling every {p.every_sec}s at h={p.detect_h}")
        stage1_sample(video, samples_dir, p.every_sec, p.detect_h)
    else:
        progress(f"[stage1] reusing existing samples in {samples_dir}")

    sample_files = sorted(glob.glob(str(samples_dir / "f_*.jpg")))
    progress(f"[stage1] {len(sample_files)} sample frames")

    app = make_face_analyser()

    candidates = []
    for i, sp in enumerate(sample_files):
        idx_in_seq = int(os.path.basename(sp).split("_")[1].split(".")[0])
        ts = (idx_in_seq - 1) * p.every_sec
        frame = cv2.imread(sp)
        if frame is None:
            continue
        h = frame.shape[0]
        min_face_px = int(p.min_face_frac * h)
        for f in app.get(frame):
            x1, y1, x2, y2 = f.bbox
            fw, fh = x2 - x1, y2 - y1
            if max(fw, fh) < min_face_px:
                continue
            fx1, fy1 = int(max(0, x1)), int(max(0, y1))
            fx2, fy2 = int(min(frame.shape[1], x2)), int(min(frame.shape[0], y2))
            face_crop = frame[fy1:fy2, fx1:fx2]
            if face_crop.size == 0:
                continue
            sharp = laplacian_var(face_crop)
            front = frontality(f)
            size = max(fw, fh)
            score = sharp * float(f.det_score) * front * (size ** 0.5)
            candidates.append({
                "score": score,
                "sharp": sharp,
                "det": float(f.det_score),
                "front": front,
                "size": float(size),
                "ts": ts,
                "sample": sp,
                "bbox_detect": f.bbox.copy(),
                "detect_h": h,
            })
        if (i + 1) % 100 == 0:
            progress(f"  scanned {i+1}/{len(sample_files)} frames, candidates={len(candidates)}")

    progress(f"[stage1] total candidates: {len(candidates)}")
    if not candidates:
        return []
    candidates.sort(key=lambda c: c["score"], reverse=True)
    top = candidates[: p.top]

    src_w, src_h = probe_resolution(video)
    progress(f"[stage2] re-extracting top {len(top)} at full {src_w}x{src_h}")

    saved: list[Path] = []
    for i, c in enumerate(top):
        full_path = headshots_dir / f"_full_top{i+1:02d}.png"
        extract_full_frame(video, c["ts"], full_path)
        full = cv2.imread(str(full_path))
        if full is None:
            progress(f"  [skip {i+1}] failed to read full frame at t={c['ts']}")
            continue
        scale = full.shape[0] / float(c["detect_h"])
        bbox_full = c["bbox_detect"] * scale
        crop = crop_headshot(full, bbox_full, margin=0.7)
        out = headshots_dir / (
            f"top{i+1:02d}_t{int(c['ts']):04d}s_score{c['score']:.0f}"
            f"_sharp{c['sharp']:.0f}_det{c['det']:.2f}_front{c['front']:.2f}.png"
        )
        cv2.imwrite(str(out), crop, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        full_path.unlink(missing_ok=True)
        saved.append(out)
        progress(
            f"  #{i+1} t={c['ts']:.1f}s sharp={c['sharp']:.0f} "
            f"det={c['det']:.2f} front={c['front']:.2f} -> {out.name}"
        )

    return saved
