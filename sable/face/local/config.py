"""Resolve external install paths (FaceFusion, roop) for the local pipeline.

Resolution order for each tool:
  1. Function argument (e.g. CLI flag).
  2. Sable config key (`face_local.facefusion_path`, `face_local.roop_path`).
  3. Environment variable (`SABLE_FACEFUSION_PATH`, `SABLE_ROOP_PATH`).
  4. Conventional default (`~/Projects/facefusion_install/`, `~/roop-env/roop/`).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


_DEFAULT_FACEFUSION = Path.home() / "Projects" / "facefusion_install"
_DEFAULT_ROOP = Path.home() / "roop-env" / "roop"


def _from_config(key: str) -> Optional[str]:
    try:
        from sable import config as cfg
        data = cfg.load_config()
        face_local = data.get("face_local") or {}
        v = face_local.get(key)
        return v if isinstance(v, str) and v else None
    except Exception:
        return None


def facefusion_path(override: Optional[Path | str] = None) -> Path:
    """Return the FaceFusion install root."""
    if override:
        return Path(override).expanduser()
    cfg_val = _from_config("facefusion_path")
    if cfg_val:
        return Path(cfg_val).expanduser()
    env_val = os.environ.get("SABLE_FACEFUSION_PATH")
    if env_val:
        return Path(env_val).expanduser()
    return _DEFAULT_FACEFUSION


def facefusion_python(override: Optional[Path | str] = None) -> Path:
    """Path to the python binary inside the FaceFusion venv."""
    return facefusion_path(override) / "venv" / "bin" / "python"


def facefusion_entry(override: Optional[Path | str] = None) -> Path:
    """Path to the FaceFusion entry script (facefusion.py)."""
    return facefusion_path(override) / "facefusion.py"


def roop_path(override: Optional[Path | str] = None) -> Path:
    """Return the roop install root (the inner `roop` dir, not the venv)."""
    if override:
        return Path(override).expanduser()
    cfg_val = _from_config("roop_path")
    if cfg_val:
        return Path(cfg_val).expanduser()
    env_val = os.environ.get("SABLE_ROOP_PATH")
    if env_val:
        return Path(env_val).expanduser()
    return _DEFAULT_ROOP
