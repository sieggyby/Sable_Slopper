"""Consent checks and audit logging for face swaps."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sable.shared.paths import audit_dir
from sable.face.library import get_reference

_AUDIT_FILE = "faceswap_log.jsonl"


def _audit_path() -> Path:
    return audit_dir() / _AUDIT_FILE


def check_consent(reference_name: str) -> bool:
    """Return True if reference has consent flag set."""
    try:
        entry = get_reference(reference_name)
        return bool(entry.get("consent", False))
    except ValueError:
        return False


def require_consent(reference_name: str) -> None:
    """Raise if reference does not have consent flag."""
    if not check_consent(reference_name):
        raise RuntimeError(
            f"Reference '{reference_name}' does not have consent flag set.\n"
            "Set it with: sable face library add <image> --name {reference_name} --consent\n"
            "Only use face swap on individuals who have consented."
        )


def log_swap(
    reference_name: str,
    target_path: str,
    output_path: str,
    model: str,
    cost_usd: float = 0.0,
    extra: Optional[dict] = None,
) -> None:
    """Append an audit log entry."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reference": reference_name,
        "target": target_path,
        "output": output_path,
        "model": model,
        "cost_usd": cost_usd,
    }
    if extra:
        entry.update(extra)

    with open(_audit_path(), "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_audit_log(limit: int = 50) -> list[dict]:
    path = _audit_path()
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries[-limit:]
