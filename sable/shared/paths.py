"""Workspace path resolution for sable."""
import re
from pathlib import Path
import os

_ORG_SLUG = re.compile(r'^[a-zA-Z0-9_-]+$')


def sable_home() -> Path:
    path = Path(os.environ.get("SABLE_HOME", str(Path.home() / ".sable")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return sable_home() / "config.yaml"


def roster_path() -> Path:
    return sable_home() / "roster.yaml"


def profiles_dir() -> Path:
    d = sable_home() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def profile_dir(handle: str) -> Path:
    # TODO(codex): consolidate handle normalization into sable/shared/utils.py
    # Pattern: strip leading @, lowercase. Currently duplicated 20+ sites inline.
    # Implement as normalize_handle(h: str) -> str. Low risk, high cosmetic value.
    handle = handle.lstrip("@")
    d = profiles_dir() / f"@{handle}"
    return d


def templates_dir() -> Path:
    d = sable_home() / "templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def wojaks_dir() -> Path:
    d = sable_home() / "wojaks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def face_library_dir() -> Path:
    d = sable_home() / "face_library"
    d.mkdir(parents=True, exist_ok=True)
    return d


def audit_dir() -> Path:
    d = sable_home() / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def workspace() -> Path:
    d = Path(os.environ.get("SABLE_WORKSPACE", str(Path.home() / "sable-workspace")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def account_output_dir(handle: str) -> Path:
    handle = handle.lstrip("@")
    d = workspace() / "output" / f"@{handle}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def transcript_cache_dir() -> Path:
    d = workspace() / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def brainrot_dir() -> Path:
    d = sable_home() / "brainrot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pulse_db_path() -> Path:
    return sable_home() / "pulse.db"


def downloads_dir() -> Path:
    """~/sable-workspace/downloads — cached yt-dlp downloads"""
    d = workspace() / "downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def explainer_resources_dir() -> Path:
    """~/.sable/explainer_resources — one subdirectory per topic slug."""
    d = sable_home() / "explainer_resources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sable_db_path() -> Path:
    return sable_home() / "sable.db"


def meta_db_path() -> Path:
    d = sable_home() / "pulse"
    d.mkdir(parents=True, exist_ok=True)
    return d / "meta.db"


def watchlist_path() -> Path:
    d = sable_home() / "pulse"
    d.mkdir(parents=True, exist_ok=True)
    return d / "watchlist.yaml"


def vault_dir(org: str = "") -> Path:
    """Root of the sable vault (or org sub-vault if org specified)."""
    from sable import config as cfg
    base = cfg.get("vault_base_path", "")
    if base:
        root = Path(base).expanduser()
    else:
        root = Path.home() / "sable-vault"
    if org:
        if not _ORG_SLUG.match(org):
            from sable.platform.errors import SableError, INVALID_ORG_ID
            raise SableError(INVALID_ORG_ID, f"Invalid org slug: {org!r}")
        d = root / org
        d.mkdir(parents=True, exist_ok=True)
        return d
    root.mkdir(parents=True, exist_ok=True)
    return root
