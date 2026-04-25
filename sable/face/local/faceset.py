"""Build a faceswap-ready face set from extracted/filtered headshots.

Outputs:
  embedding.npy   — score-weighted average ArcFace identity vector (512-dim, L2-normalised)
  curated/        — diversity-curated subset (greedy farthest-point in embedding space)
  composite.png   — landmark-aligned pixel mean (visual reference only — DO NOT swap from this)
"""
from __future__ import annotations

import glob
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sable.face.local.common import composite_image, make_face_analyser


# Standard ArcFace 112x112 reference landmarks
_ARCFACE_REF = [
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
]


@dataclass
class FacesetParams:
    curate_n: int = 6


def _parse_score(path: str) -> float:
    m = re.search(r"score(\d+)", os.path.basename(path))
    return float(m.group(1)) if m else 1.0


def _align_112(img, kps):
    import cv2
    import numpy as np
    from skimage import transform as sktrans
    tform = sktrans.SimilarityTransform()
    tform.estimate(kps, np.asarray(_ARCFACE_REF, dtype=np.float32))
    M = tform.params[0:2, :]
    return cv2.warpAffine(img, M, (112, 112), borderValue=0.0)


def _greedy_diverse(embeddings, k: int) -> list[int]:
    import numpy as np
    n = len(embeddings)
    if n <= k:
        return list(range(n))
    selected = [0]
    dists = 1.0 - embeddings @ embeddings[0]
    for _ in range(k - 1):
        nxt = int(np.argmax(dists))
        selected.append(nxt)
        new_d = 1.0 - embeddings @ embeddings[nxt]
        dists = np.minimum(dists, new_d)
    return selected


def build_faceset(
    workspace: Path,
    params: Optional[FacesetParams] = None,
    *,
    source_subdir: str = "headshots",
    progress=print,
) -> dict:
    """Build embedding + curated subset + composite from `<workspace>/<source_subdir>/`.

    `source_subdir` defaults to 'headshots' (output of extract). Pass 'matches' to
    build from filter/closed-mouth output instead.
    """
    import cv2
    import numpy as np

    p = params or FacesetParams()
    src = workspace / source_subdir
    out_emb = workspace / "embedding.npy"
    curated_dir = workspace / "curated"
    composite_path = workspace / "composite.png"

    files = sorted(glob.glob(str(src / "top*.png"))) + sorted(glob.glob(str(src / "closed_top*.png")))
    if not files:
        raise FileNotFoundError(f"No top*.png files in {src}")

    app = make_face_analyser()

    rows = []
    aligned = []
    for fp in files:
        img = cv2.imread(fp)
        if img is None:
            continue
        faces = app.get(img)
        if not faces:
            progress(f"  [warn] no face in {os.path.basename(fp)}")
            continue
        f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        emb = f.normed_embedding
        score = _parse_score(fp)
        rows.append({"path": fp, "emb": emb, "score": score, "kps": f.kps})
        aligned.append(_align_112(img, f.kps))
        progress(f"  {os.path.basename(fp):60s} score={score:.0f}")

    if not rows:
        raise RuntimeError("No usable faces in source images.")

    embs = np.stack([r["emb"] for r in rows])
    scores = np.array([r["score"] for r in rows], dtype=np.float64)
    w = scores / scores.sum()
    avg = (embs * w[:, None]).sum(axis=0)
    avg = avg / np.linalg.norm(avg)
    np.save(out_emb, avg)
    progress(f"\nSaved averaged embedding ({embs.shape[0]} faces) -> {out_emb}")

    sims = embs @ avg
    progress("\nPer-crop similarity to averaged identity:")
    for r, s in zip(rows, sims):
        progress(f"  {s:.4f}  {os.path.basename(r['path'])}")

    if curated_dir.is_dir():
        shutil.rmtree(curated_dir)
    curated_dir.mkdir(parents=True, exist_ok=True)
    picks = _greedy_diverse(embs, p.curate_n)
    progress(f"\nCurated {len(picks)} diverse crops -> {curated_dir}")
    curated_paths: list[Path] = []
    for rank, idx in enumerate(picks, 1):
        src_path = rows[idx]["path"]
        dst = curated_dir / f"c{rank:02d}_{os.path.basename(src_path)}"
        shutil.copy2(src_path, dst)
        curated_paths.append(dst)
        progress(f"  c{rank:02d}  sim={sims[idx]:.3f}  {os.path.basename(src_path)}")

    if aligned:
        comp = composite_image(aligned, w)
        cv2.imwrite(str(composite_path), comp)
        progress(f"\nWrote aligned pixel-average -> {composite_path} (visual reference only)")

    return {
        "embedding": str(out_emb),
        "curated_count": len(curated_paths),
        "curated": [str(c) for c in curated_paths],
        "composite": str(composite_path) if aligned else None,
    }
