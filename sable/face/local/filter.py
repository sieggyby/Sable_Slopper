"""Identity-filter candidates against a reference image.

Caches all face detections (with embeddings) to a pickle so re-runs with a
different threshold don't re-do the expensive detection step.
"""
from __future__ import annotations

import glob
import os
import pickle
import sys
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
)


@dataclass
class FilterParams:
    every_sec: float = 2.0
    min_face_frac: float = 0.08
    threshold: float = 0.45  # ArcFace cosine sim — ~0.4-0.5 is "same person"
    top: int = 15
    bucket_size_s: float = 6.0  # time-spread picks across the source


def get_reference_embedding(app, ref_path: Path):
    import cv2
    img = cv2.imread(str(ref_path))
    if img is None:
        raise FileNotFoundError(f"Could not read reference {ref_path}")
    faces = app.get(img)
    if not faces:
        raise ValueError(f"No face found in reference {ref_path}")
    f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    return f.normed_embedding


def detect_all_samples(
    app, samples_dir: Path, every_sec: float, min_face_frac: float, cache_path: Path,
    *, progress=print,
) -> list:
    import cv2
    if cache_path.exists():
        progress(f"[detect] loading cache {cache_path}")
        with open(cache_path, "rb") as fh:
            return pickle.load(fh)

    sample_files = sorted(glob.glob(str(samples_dir / "f_*.jpg")))
    progress(f"[detect] scanning {len(sample_files)} sample frames")
    candidates = []
    for i, sp in enumerate(sample_files):
        idx_in_seq = int(os.path.basename(sp).split("_")[1].split(".")[0])
        ts = (idx_in_seq - 1) * every_sec
        frame = cv2.imread(sp)
        if frame is None:
            continue
        h = frame.shape[0]
        min_face_px = int(min_face_frac * h)
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
            candidates.append({
                "sharp": sharp,
                "det": float(f.det_score),
                "front": front,
                "size": float(size),
                "ts": ts,
                "sample": sp,
                "bbox_detect": f.bbox.copy(),
                "detect_h": h,
                "embedding": f.normed_embedding.copy(),
            })
        if (i + 1) % 200 == 0:
            progress(f"  scanned {i+1}/{len(sample_files)}, candidates={len(candidates)}")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as fh:
        pickle.dump(candidates, fh)
    progress(f"[detect] cached {len(candidates)} candidates -> {cache_path}")
    return candidates


def filter_by_reference(
    video: Path,
    workspace: Path,
    reference: Path,
    params: Optional[FilterParams] = None,
    *,
    progress=print,
) -> list[Path]:
    """Identity-filter candidates against `reference` and save full-res crops."""
    import cv2
    import numpy as np

    p = params or FilterParams()
    samples_dir = workspace / "samples"
    matches_dir = workspace / "matches"
    cache_path = workspace / "candidates.pkl"
    matches_dir.mkdir(parents=True, exist_ok=True)

    if not glob.glob(str(samples_dir / "f_*.jpg")):
        from sable.face.local.common import stage1_sample
        progress(f"[stage1] no samples found, sampling every {p.every_sec}s")
        stage1_sample(video, samples_dir, p.every_sec, 1080)

    app = make_face_analyser()
    ref_emb = get_reference_embedding(app, reference)
    progress(f"[ref] loaded reference embedding from {reference.name}")

    candidates = detect_all_samples(
        app, samples_dir, p.every_sec, p.min_face_frac, cache_path, progress=progress
    )
    if not candidates:
        progress("[filter] no face detections at all — bad input?")
        return []

    embs = np.stack([c["embedding"] for c in candidates])
    sims = embs @ ref_emb
    for c, s in zip(candidates, sims):
        c["sim"] = float(s)

    progress(
        f"[sim] min={sims.min():.3f} median={np.median(sims):.3f} "
        f"mean={sims.mean():.3f} max={sims.max():.3f}"
    )
    for b in [0.2, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8]:
        progress(f"  >= {b:.2f}: {(sims >= b).sum()}")

    matched = [c for c in candidates if c["sim"] >= p.threshold]
    progress(f"[filter] {len(matched)} matches at threshold {p.threshold}")
    if not matched:
        return []

    for c in matched:
        c["score"] = (
            c["sharp"] * c["det"] * c["front"] * (c["size"] ** 0.5)
            * (0.5 + 0.5 * c["sim"])
        )
    matched.sort(key=lambda x: x["score"], reverse=True)

    # Time-bucket dedup so picks are spread across the video
    picked = []
    used_buckets = set()
    for c in matched:
        b = int(c["ts"] // p.bucket_size_s)
        if b in used_buckets:
            continue
        used_buckets.add(b)
        picked.append(c)
        if len(picked) >= p.top:
            break
    if len(picked) < p.top:
        for c in matched:
            if c not in picked:
                picked.append(c)
                if len(picked) >= p.top:
                    break

    progress(f"[pick] {len(picked)} time-spread picks")
    src_w, src_h = probe_resolution(video)
    progress(f"[stage2] re-extracting at full {src_w}x{src_h}")

    saved: list[Path] = []
    for i, c in enumerate(picked):
        full_path = matches_dir / f"_full_{i+1:02d}.png"
        extract_full_frame(video, c["ts"], full_path)
        full = cv2.imread(str(full_path))
        if full is None:
            progress(f"  [skip {i+1}] failed to read full frame at t={c['ts']}")
            continue
        # Re-detect at full res, match by embedding for a sharper bbox
        faces_full = app.get(full)
        best_face, best_sim = None, -1.0
        for f in faces_full:
            s = float(f.normed_embedding @ c["embedding"])
            if s > best_sim:
                best_sim = s
                best_face = f
        if best_face is None or best_sim < 0.5:
            scale = full.shape[0] / float(c["detect_h"])
            bbox_full = c["bbox_detect"] * scale
        else:
            bbox_full = best_face.bbox

        crop = crop_headshot(full, bbox_full, margin=0.7)
        out = matches_dir / (
            f"top{i+1:02d}_t{int(c['ts']):04d}s_sim{c['sim']:.2f}"
            f"_score{c['score']:.0f}"
            f"_sharp{c['sharp']:.0f}_det{c['det']:.2f}_front{c['front']:.2f}.png"
        )
        cv2.imwrite(str(out), crop, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        full_path.unlink(missing_ok=True)
        saved.append(out)
        progress(
            f"  #{i+1} t={c['ts']:.1f}s sim={c['sim']:.3f} "
            f"sharp={c['sharp']:.0f} -> {out.name}"
        )

    return saved
