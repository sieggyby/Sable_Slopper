"""Workspace path resolution for sable."""
from pathlib import Path
import os


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
