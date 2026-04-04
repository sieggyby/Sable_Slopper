"""Brainrot library management and energy-matched selection."""
from __future__ import annotations

import random
import yaml
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from sable.shared.paths import brainrot_dir
from sable.shared.ffmpeg import get_duration, run, require_ffmpeg

_INDEX_FILE = "_index.yaml"

ENERGY_LEVELS = ("low", "medium", "high")


def _index_path() -> Path:
    return brainrot_dir() / _INDEX_FILE


def load_index() -> list[dict]:
    path = _index_path()
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or []
    return data if isinstance(data, list) else []


def save_index(entries: list[dict]) -> None:
    with open(_index_path(), "w") as f:
        yaml.dump(entries, f, default_flow_style=False)


def add_video(
    path: str | Path,
    energy: str = "medium",
    tags: Optional[list[str]] = None,
    copy: bool = True,
) -> dict:
    """Register a brainrot video in the library."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if energy not in ENERGY_LEVELS:
        raise ValueError(f"energy must be one of {ENERGY_LEVELS}")

    if copy:
        dest = brainrot_dir() / path.name
        if not dest.exists():
            import shutil
            shutil.copy2(str(path), str(dest))
        stored_path = str(dest)
    else:
        stored_path = str(path.resolve())

    duration = get_duration(stored_path)
    entry = {
        "path": stored_path,
        "filename": path.name,
        "energy": energy,
        "duration": round(duration, 2),
        "tags": tags or [],
    }
    index = load_index()
    # Avoid duplicates
    index = [e for e in index if e.get("filename") != path.name]
    index.append(entry)
    save_index(index)
    return entry


def pick(
    energy: str = "medium",
    min_duration: float = 0.0,
    tags: Optional[list[str]] = None,
    clip_duration: float = 0.0,
) -> Optional[str]:
    """
    Select a random brainrot video matching energy level.
    Falls back to adjacent energy levels if no exact match.
    When clip_duration > 0, prefers sources >= clip_duration / 2 (max 2x loop).
    When tags are provided, prefers theme-matched sources but falls back to any.
    Returns file path or None.
    """
    if energy == "none":
        return None
    index = load_index()
    # Filter to existing files
    index = [e for e in index if Path(e.get("path", "")).exists()]

    def _base_matches(entry: dict, eng: str) -> bool:
        if entry["energy"] != eng:
            return False
        if entry.get("duration", 0) < min_duration:
            return False
        return True

    def _has_theme(entry: dict) -> bool:
        if not tags:
            return False
        return any(t in entry.get("tags", []) for t in tags)

    # Try exact energy, then adjacent
    fallback_order = _energy_fallback(energy)
    for eng in fallback_order:
        candidates = [e for e in index if _base_matches(e, eng)]
        if not candidates:
            continue
        result = _pick_best(candidates, clip_duration, _has_theme if tags else None)
        if result is not None:
            return result
    return None


def _pick_best(
    candidates: list[dict],
    clip_duration: float,
    theme_fn: Optional[Callable[[dict], bool]] = None,
) -> Optional[str]:
    """Pick from candidates with layered preference: theme > duration > any."""
    # Layer 1: theme-matched + duration-preferred
    if theme_fn is not None:
        themed = [c for c in candidates if theme_fn(c)]
        if themed:
            if clip_duration > 0:
                long_themed = [c for c in themed if c.get("duration", 0) >= clip_duration / 2.0]
                if long_themed:
                    return random.choice(long_themed)["path"]
            return random.choice(themed)["path"]

    # Layer 2: duration-preferred (no theme match or no tags)
    if clip_duration > 0:
        preferred = [c for c in candidates if c.get("duration", 0) >= clip_duration / 2.0]
        if preferred:
            return random.choice(preferred)["path"]

    # Layer 3: any candidate
    return random.choice(candidates)["path"]


def _energy_fallback(energy: str) -> list[str]:
    idx = ENERGY_LEVELS.index(energy) if energy in ENERGY_LEVELS else 1
    order = [energy]
    if idx > 0:
        order.append(ENERGY_LEVELS[idx - 1])
    if idx < len(ENERGY_LEVELS) - 1:
        order.append(ENERGY_LEVELS[idx + 1])
    return order


def list_videos(energy: Optional[str] = None) -> list[dict]:
    index = load_index()
    if energy:
        index = [e for e in index if e.get("energy") == energy]
    return index


def loop_to_duration(video_path: str | Path, target_duration: float, output_path: str | Path) -> None:
    """Loop a brainrot video to match target duration using ffmpeg."""
    src_duration = get_duration(video_path)
    if src_duration <= 0:
        raise ValueError(f"Cannot determine duration of {video_path}")

    loops = int(target_duration / src_duration) + 2
    # AR5-28: cap loops to prevent runaway ffmpeg for very short brainrot clips
    _MAX_LOOPS = 30  # why: 30 loops × even a 1s clip = 30s, well beyond any real target
    if loops > _MAX_LOOPS:
        import warnings
        warnings.warn(
            f"loop_to_duration: capping loops {loops} → {_MAX_LOOPS} for {video_path}",
            RuntimeWarning,
            stacklevel=2,
        )
        loops = _MAX_LOOPS
    run([
        require_ffmpeg(), "-y",
        "-stream_loop", str(loops),
        "-i", str(video_path),
        "-t", str(target_duration),
        "-c", "copy",
        str(output_path),
    ], capture=True)
