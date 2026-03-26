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
    "pulse_meta": {
        "lookback_hours": 48,
        "baseline_long_days": 30,
        "baseline_short_days": 7,
        "min_baseline_days": 5,
        "min_samples_for_trend": 4,
        "min_authors_for_trend": 2,
        "concentration_threshold": 0.50,
        "surging_threshold": 2.5,
        "rising_threshold": 1.5,
        "declining_threshold": 0.8,
        "dead_threshold": 0.5,
        "lift_threshold": 1.5,
        "aggregation_method": "weighted_mean",
        "max_cost_per_run": 1.00,
        "claude_model": "claude-sonnet-4-6",
        "top_n_for_analysis": 20,
        "engagement_weights": {
            "likes": 1.0,
            "replies": 12.0,
            "reposts": 20.0,
            "quotes": 25.0,
            "bookmarks": 10.0,
            "video_views": 6.0,
        },
    },
    "platform": {
        "cost_caps": {
            "max_ai_usd_per_org_per_week": 5.00,
            "max_ai_usd_per_playbook": 0.15,
            "max_ai_usd_per_strategy_brief": 0.20,
            "max_ai_usd_per_vault_sync": 0.00,
            "max_external_api_calls_per_feedback_loop": 500,
            "max_retries_per_step": 2,
        },
        "model_ladder": {
            "primary": "claude-sonnet-4-20250514",
            "fallback": "claude-haiku-4-5-20251001",
            "template_only": None,
        },
        "degrade_mode": "fallback",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    path = config_path()
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    return _deep_merge(_DEFAULTS, data)


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
