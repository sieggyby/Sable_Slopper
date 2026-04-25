"""Shell out to a local FaceFusion install for image/video face swap.

This is the operator-laptop-only path. The hosted Replicate path lives in
`sable.face.swapper`. See FACE_SWAP_LESSONS.md for tuning recipes and known
failure modes (notably: don't stack GFPGAN on top of a swap; codeformer at
weight 0.4 + blend 50 keeps identity).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sable.face.local import config as fl_cfg


@dataclass
class SwapParams:
    swap_model: str = "hyperswap_1c_256"
    pixel_boost: str = "512x512"
    detector_model: str = "retinaface"
    occluder_model: str = "xseg_3"
    selector_mode: str = "reference"
    video_encoder: str = "h264_videotoolbox"
    quality: int = 95
    enhance: bool = False
    enhancer_model: str = "codeformer"
    enhancer_weight: float = 0.4
    enhancer_blend: int = 50
    execution_providers: tuple[str, ...] = ("coreml",)


def build_command(
    source: Path,
    target: Path,
    output: Path,
    params: Optional[SwapParams] = None,
    *,
    facefusion_override: Optional[Path | str] = None,
) -> list[str]:
    """Construct the FaceFusion headless-run command. Returns argv."""
    p = params or SwapParams()
    py = fl_cfg.facefusion_python(facefusion_override)
    entry = fl_cfg.facefusion_entry(facefusion_override)

    processors = ["face_swapper"]
    if p.enhance:
        processors.append("face_enhancer")

    argv = [
        str(py), str(entry), "headless-run",
        "--execution-providers", *p.execution_providers,
        "--processors", *processors,
        "--face-swapper-model", p.swap_model,
        "--face-swapper-pixel-boost", p.pixel_boost,
        "--face-detector-model", p.detector_model,
        "--face-occluder-model", p.occluder_model,
        "--face-selector-mode", p.selector_mode,
        "--output-video-encoder", p.video_encoder,
        "--output-video-quality", str(p.quality),
        "-s", str(source),
        "-t", str(target),
        "-o", str(output),
    ]
    if p.enhance:
        argv.extend([
            "--face-enhancer-model", p.enhancer_model,
            "--face-enhancer-weight", str(p.enhancer_weight),
            "--face-enhancer-blend", str(p.enhancer_blend),
        ])
    return argv


def run_swap(
    source: Path,
    target: Path,
    output: Path,
    params: Optional[SwapParams] = None,
    *,
    facefusion_override: Optional[Path | str] = None,
    log_path: Optional[Path] = None,
) -> dict:
    """Run a FaceFusion swap. Returns metadata dict.

    On success, also writes a `<output>_meta.json` sidecar so downstream tooling
    (vault sync, audit log) can ingest the run.
    """
    import json as _json
    import time
    from datetime import datetime, timezone

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    argv = build_command(source, target, output, params, facefusion_override=facefusion_override)
    cwd = fl_cfg.facefusion_path(facefusion_override)

    t0 = time.time()
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w") as logf:
            r = subprocess.run(argv, cwd=str(cwd), stdout=logf, stderr=subprocess.STDOUT, text=True)
    else:
        r = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)
    elapsed = time.time() - t0

    if r.returncode != 0:
        msg = r.stderr if hasattr(r, "stderr") and r.stderr else f"exit code {r.returncode}"
        raise RuntimeError(f"FaceFusion failed after {elapsed:.0f}s: {msg[:500]}")

    if not output.exists():
        raise RuntimeError(
            f"FaceFusion completed (rc=0) in {elapsed:.0f}s but no output at {output}. "
            "Check the log for silent no-op (see FACE_SWAP_LESSONS.md bug #4)."
        )

    p = params or SwapParams()
    meta = {
        "source": str(source),
        "target": str(target),
        "output": str(output),
        "tool": "facefusion-local",
        "swap_model": p.swap_model,
        "pixel_boost": p.pixel_boost,
        "enhance": p.enhance,
        "enhancer_model": p.enhancer_model if p.enhance else None,
        "enhancer_weight": p.enhancer_weight if p.enhance else None,
        "enhancer_blend": p.enhancer_blend if p.enhance else None,
        "elapsed_s": round(elapsed, 1),
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
    Path(str(output) + "_meta.json").write_text(_json.dumps(meta, indent=2))
    return meta
