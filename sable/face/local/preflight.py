"""Smoke-check the local face-swap install before kicking off a real run."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sable.face.local import config as fl_cfg


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def run_checks(facefusion_override: Optional[Path | str] = None) -> list[Check]:
    """Run all preflight checks and return their results."""
    checks: list[Check] = []

    # ffmpeg / ffprobe
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        checks.append(Check(tool, bool(path), path or "not on PATH"))

    # Heavy Python deps that the pipeline imports lazily
    for mod in ("cv2", "numpy", "insightface", "skimage"):
        try:
            __import__(mod)
            checks.append(Check(mod, True, "importable"))
        except ImportError as e:
            checks.append(Check(mod, False, f"missing — {e}"))

    # FaceFusion install
    ff_root = fl_cfg.facefusion_path(facefusion_override)
    ff_python = fl_cfg.facefusion_python(facefusion_override)
    ff_entry = fl_cfg.facefusion_entry(facefusion_override)
    checks.append(Check(
        "facefusion_root",
        ff_root.is_dir(),
        str(ff_root),
    ))
    checks.append(Check(
        "facefusion_venv_python",
        ff_python.is_file(),
        str(ff_python),
    ))
    checks.append(Check(
        "facefusion_entry",
        ff_entry.is_file(),
        str(ff_entry),
    ))

    if ff_python.is_file() and ff_entry.is_file():
        try:
            r = subprocess.run(
                [str(ff_python), str(ff_entry), "--version"],
                cwd=str(ff_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode == 0:
                checks.append(Check("facefusion_smoke", True, r.stdout.strip().splitlines()[-1] if r.stdout else "ok"))
            else:
                checks.append(Check("facefusion_smoke", False, (r.stderr or r.stdout)[:200]))
        except Exception as e:
            checks.append(Check("facefusion_smoke", False, str(e)[:200]))
    else:
        checks.append(Check("facefusion_smoke", False, "skipped — install not found"))

    return checks


def all_ok(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)
