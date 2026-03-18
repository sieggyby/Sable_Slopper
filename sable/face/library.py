"""Face reference library — _index.yaml CRUD with consent tracking."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import shutil
import yaml

from sable.shared.paths import face_library_dir

_INDEX_FILE = "_index.yaml"


def _index_path() -> Path:
    return face_library_dir() / _INDEX_FILE


def load_index() -> list[dict]:
    path = _index_path()
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or []
    return data if isinstance(data, list) else []


def save_index(entries: list[dict]) -> None:
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(entries, f, default_flow_style=False)


def add_reference(
    image_path: str | Path,
    name: str,
    consent: bool = False,
    notes: str = "",
    copy: bool = True,
) -> dict:
    """Register a reference face image."""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Reference image not found: {image_path}")

    if copy:
        dest = face_library_dir() / image_path.name
        if not dest.exists():
            shutil.copy2(str(image_path), str(dest))
        stored = str(dest)
    else:
        stored = str(image_path.resolve())

    entry = {
        "name": name,
        "path": stored,
        "filename": image_path.name,
        "consent": consent,
        "notes": notes,
    }

    index = load_index()
    index = [e for e in index if e.get("name") != name]
    index.append(entry)
    save_index(index)
    return entry


def get_reference(name: str) -> dict:
    index = load_index()
    for entry in index:
        if entry.get("name") == name:
            return entry
    raise ValueError(
        f"Reference face '{name}' not found. "
        f"Add it with: sable face library add <image> --name {name}"
    )


def list_references(consent_only: bool = False) -> list[dict]:
    index = load_index()
    if consent_only:
        index = [e for e in index if e.get("consent")]
    return index


def remove_reference(name: str) -> bool:
    index = load_index()
    before = len(index)
    index = [e for e in index if e.get("name") != name]
    if len(index) < before:
        save_index(index)
        return True
    return False
