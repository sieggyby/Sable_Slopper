"""Shared frontmatter read/write helpers for vault notes."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

from sable.shared.files import atomic_write

# ---------------------------------------------------------------------------
# In-memory TTL cache for load_all_notes
# ---------------------------------------------------------------------------

_notes_cache: dict[str, tuple[float, list[dict]]] = {}
_notes_lock = threading.Lock()
_CACHE_TTL = 300  # 5 minutes


_SYNC_INDEX_FILE = "_sync_index.json"


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

def read_note(path: str | Path) -> tuple[dict, str]:
    """Parse YAML frontmatter + body from a markdown note.

    Returns (frontmatter_dict, body_str).
    """
    content = Path(path).read_text(encoding="utf-8")
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
            return fm, body
    return {}, content.strip()


def write_note(path: str | Path, frontmatter: dict, body: str = "") -> None:
    """Write markdown note with YAML frontmatter."""
    path = Path(path)
    fm_yaml = yaml.dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    content = f"---\n{fm_yaml}---\n"
    if body:
        content += f"\n{body}\n"
    atomic_write(path, content)
    # Invalidate any cached notes — path may be inside a vault content/ dir
    with _notes_lock:
        _notes_cache.clear()


def read_frontmatter(path: str | Path) -> dict:
    """Read only the frontmatter from a note (faster than read_note for bulk ops)."""
    fm, _ = read_note(path)
    return fm


# ---------------------------------------------------------------------------
# Bulk loading
# ---------------------------------------------------------------------------

def load_all_notes(vault_path: Path) -> list[dict]:
    """Load frontmatter from all content/ notes into a list of dicts.

    Each dict includes a synthetic '_note_path' key for reference.
    Results are cached in-memory with a 5-minute TTL.
    """
    key = str(vault_path)
    now = time.monotonic()
    with _notes_lock:
        if key in _notes_cache:
            cached_at, cached = _notes_cache[key]
            if now - cached_at < _CACHE_TTL:
                return list(cached)

    content_dir = vault_path / "content"
    if not content_dir.exists():
        return []
    results = []
    for md_file in content_dir.rglob("*.md"):
        try:
            fm = read_frontmatter(md_file)
            fm["_note_path"] = str(md_file)
            results.append(fm)
        except Exception as e:
            logger.warning("Skipping malformed note %s: %s", md_file, e)
    with _notes_lock:
        _notes_cache[key] = (now, results)
    return list(results)


def invalidate_notes_cache(vault_path: Path | None = None) -> None:
    """Clear the load_all_notes cache (all vaults or a specific one)."""
    with _notes_lock:
        if vault_path:
            _notes_cache.pop(str(vault_path), None)
        else:
            _notes_cache.clear()


# ---------------------------------------------------------------------------
# Sync index
# ---------------------------------------------------------------------------

def load_sync_index(vault_path: Path) -> dict:
    """Load {abs_output_path: content_id} mapping from _sync_index.json."""
    idx_file = vault_path / _SYNC_INDEX_FILE
    if not idx_file.exists():
        return {}
    try:
        return json.loads(idx_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_sync_index(vault_path: Path, index: dict) -> None:
    """Persist sync index to disk."""
    idx_file = vault_path / _SYNC_INDEX_FILE
    atomic_write(idx_file, json.dumps(index, indent=2))
