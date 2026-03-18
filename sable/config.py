"""Load and save ~/.sable/config.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import yaml

from sable.shared.paths import config_path

_DEFAULTS: dict = {
    "anthropic_api_key": "",
    "replicate_api_key": "",
    "socialdata_api_key": "",
    "default_model": "claude-sonnet-4-6",
    "workspace": str(Path.home() / "sable-workspace"),
}


def load_config() -> dict:
    path = config_path()
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    return {**_DEFAULTS, **data}


def save_config(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)


def get(key: str, default=None):
    return load_config().get(key, default)


def set_key(key: str, value: str) -> None:
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)


def require_key(key: str) -> str:
    """Return config value or raise with helpful message."""
    import os
    # Check env first
    env_map = {
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "replicate_api_key": "REPLICATE_API_TOKEN",
        "socialdata_api_key": "SOCIALDATA_API_KEY",
    }
    if key in env_map:
        val = os.environ.get(env_map[key]) or get(key)
    else:
        val = get(key)
    if not val:
        raise RuntimeError(
            f"Missing config key '{key}'. Set it with: sable config set {key} <value>"
        )
    return val
