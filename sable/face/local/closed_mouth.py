"""Secondary scoring pass: pick the closed-mouth subset of identity-matches.

Loads the cached candidates.pkl from a prior `filter` run, re-detects each
sample frame to grab 106-pt landmarks, computes mouth-aspect-ratio (MAR), and
keeps the lowest-MAR picks. Useful for face swaps where an open mouth makes the
swap look uncanny.
"""
from __future__ import annotations

import os
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sable.face.local.common import (
    crop_headshot,
    extract_full_frame,
    make_face_analyser,
    probe_resolution,
)


@dataclass
class ClosedParams:
    id_threshold: float = 0.45
    mar_max: float = 0.40
    top: int = 10
    bucket_size_s: float = 8.0
    min_gap_from_existing_s: float = 4.0


def _mar(lms) -> float:
    pts = lms[52:72]
    h = pts[:, 1].max() - pts[:, 1].min()
    w = pts[:, 0].max() - pts[:, 0].min()
    return float(h / max(w, 1e-6))


def _existing_timestamps(out_dir: Path) -> set[int]:
    ts_set: set[int] = set()
    if not out_dir.exists():
        return ts_set
    for fn in os.listdir(out_dir):
        m = re.search(r"t(\d+)s", fn)
        if m:
            ts_set.add(int(m.group(1)))
    return ts_set


def closed_mouth(
    video: Path,
    workspace: Path,
    reference: Path,
    params: Optional[ClosedParams] = None,
    *,
    progress=print,
) -> list[Path]:
    """Add closed-mouth picks to `workspace/matches/`. Requires a prior filter run."""
    import cv2
    import numpy as np

    p = params or ClosedParams()
    matches_dir = workspace / "matches"
    cache_path = workspace / "candidates.pkl"
    matches_dir.mkdir(parents=True, exist_ok=True)
    existing_ts = _existing_timestamps(matches_dir)
    progress(f"[init] existing saved timestamps: {sorted(existing_ts)}")

    if not cache_path.exists():
        raise FileNotFoundError(
            f"{cache_path} not found — run `sable face local filter` first."
        )

    app = make_face_analyser()
    ref_img = cv2.imread(str(reference))
    if ref_img is None:
        raise FileNotFoundError(f"Could not read reference {reference}")
    ref_faces = app.get(ref_img)
    if not ref_faces:
        raise ValueError(f"No face in reference {reference}")
    ref_face = max(ref_faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    ref_emb = ref_face.normed_embedding
    progress(f"[ref] reference MAR = {_mar(ref_face.landmark_2d_106):.3f}")

    with open(cache_path, "rb") as fh:
        candidates = pickle.load(fh)
    progress(f"[cache] {len(candidates)} candidates loaded")

    matches = []
    for c in candidates:
        sim = float(c["embedding"] @ ref_emb)
        if sim >= p.id_threshold:
            c["sim"] = sim
            matches.append(c)
    progress(f"[filter] {len(matches)} matches at id_thresh={p.id_threshold}")

    by_sample: dict[str, list] = {}
    for c in matches:
        by_sample.setdefault(c["sample"], []).append(c)
    progress(f"[group] {len(by_sample)} unique sample frames")

    enriched = []
    for i, (sp, group) in enumerate(by_sample.items()):
        img = cv2.imread(sp)
        if img is None:
            continue
        faces = app.get(img)
        for c in group:
            best_face, best_sim = None, -1.0
            for f in faces:
                s = float(f.normed_embedding @ c["embedding"])
                if s > best_sim:
                    best_sim = s
                    best_face = f
            if best_face is None or best_sim < 0.95:
                continue
            c["mar"] = _mar(best_face.landmark_2d_106)
            c["bbox_detect"] = best_face.bbox.copy()
            enriched.append(c)
        if (i + 1) % 200 == 0:
            progress(f"  enriched {i+1}/{len(by_sample)} frames")
    progress(f"[enrich] {len(enriched)} candidates with MAR")

    if not enriched:
        progress("[done] no enriched candidates — bad reference?")
        return []

    mars = np.array([c["mar"] for c in enriched])
    progress(
        f"[mar] min={mars.min():.3f} median={np.median(mars):.3f} "
        f"mean={mars.mean():.3f} max={mars.max():.3f}"
    )
    for thr in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45]:
        progress(f"  MAR < {thr:.2f}: {(mars < thr).sum()}")

    closed = [c for c in enriched if c["mar"] < p.mar_max]
    progress(f"[filter] {len(closed)} closed-mouth (MAR < {p.mar_max})")
    if not closed:
        return []

    for c in closed:
        c["score"] = (
            c["sharp"] * c["det"] * c["front"] * (c["size"] ** 0.5)
            * (0.5 + 0.5 * c["sim"])
            * (1.0 - c["mar"])
        )
    closed.sort(key=lambda x: x["score"], reverse=True)

    picked = []
    used_buckets = set()
    for c in closed:
        ts_int = int(c["ts"])
        if any(abs(ts_int - et) <= p.min_gap_from_existing_s for et in existing_ts):
            continue
        b = int(c["ts"] // p.bucket_size_s)
        if b in used_buckets:
            continue
        used_buckets.add(b)
        picked.append(c)
        if len(picked) >= p.top:
            break
    progress(f"[pick] {len(picked)} closed-mouth picks")

    src_w, src_h = probe_resolution(video)
    progress(f"[stage2] source {src_w}x{src_h}")

    saved: list[Path] = []
    for i, c in enumerate(picked):
        full_path = matches_dir / f"_full_closed_{i+1:02d}.png"
        extract_full_frame(video, c["ts"], full_path)
        full = cv2.imread(str(full_path))
        if full is None:
            progress(f"  [skip {i+1}] read failed at t={c['ts']}")
            continue
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
            f"closed_top{i+1:02d}_t{int(c['ts']):04d}s_mar{c['mar']:.2f}"
            f"_sim{c['sim']:.2f}_score{c['score']:.0f}"
            f"_sharp{c['sharp']:.0f}_front{c['front']:.2f}.png"
        )
        cv2.imwrite(str(out), crop, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        full_path.unlink(missing_ok=True)
        saved.append(out)
        progress(
            f"  closed#{i+1} t={c['ts']:.1f}s mar={c['mar']:.3f} "
            f"sim={c['sim']:.3f} -> {out.name}"
        )

    return saved
