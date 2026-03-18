"""Template registry loader and validation."""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Optional

from sable.shared.paths import templates_dir

_REGISTRY_FILE = "_registry.yaml"

_DEFAULT_TEMPLATES = [
    {
        "id": "drake",
        "name": "Drake Pointing",
        "description": "Disapproval top, approval bottom. Two text zones.",
        "zones": [
            {"id": "top", "label": "Disapproval", "x": 0.55, "y": 0.1, "w": 0.42, "h": 0.38},
            {"id": "bottom", "label": "Approval", "x": 0.55, "y": 0.55, "w": 0.42, "h": 0.38},
        ],
        "style": "minimal",
        "image_file": "drake.jpg",
        "prompt_hint": "Two contrasting things: what to avoid vs. what to do",
    },
    {
        "id": "distracted-boyfriend",
        "name": "Distracted Boyfriend",
        "description": "Three labels on the classic look-back photo.",
        "zones": [
            {"id": "boyfriend", "label": "Boyfriend (subject)", "x": 0.1, "y": 0.7, "w": 0.25, "h": 0.15},
            {"id": "girlfriend", "label": "Girlfriend (old thing)", "x": 0.45, "y": 0.7, "w": 0.2, "h": 0.15},
            {"id": "other", "label": "Other girl (new thing)", "x": 0.65, "y": 0.1, "w": 0.25, "h": 0.15},
        ],
        "style": "classic",
        "image_file": "distracted_boyfriend.jpg",
        "prompt_hint": "Subject leaving old thing for shiny new thing",
    },
    {
        "id": "this-is-fine",
        "name": "This Is Fine",
        "description": "Dog in burning room. One caption.",
        "zones": [
            {"id": "caption", "label": "Caption", "x": 0.05, "y": 0.05, "w": 0.9, "h": 0.25},
        ],
        "style": "classic",
        "image_file": "this_is_fine.jpg",
        "prompt_hint": "Denial of an obvious crisis",
    },
    {
        "id": "wojak-crying",
        "name": "Wojak Crying",
        "description": "Classic wojak melt. Caption at top or bottom.",
        "zones": [
            {"id": "caption", "label": "Caption", "x": 0.05, "y": 0.75, "w": 0.9, "h": 0.2},
        ],
        "style": "modern",
        "image_file": "wojak_crying.png",
        "prompt_hint": "Relatable pain or loss",
    },
    {
        "id": "two-buttons",
        "name": "Two Buttons",
        "description": "Sweating guy choosing between two buttons.",
        "zones": [
            {"id": "button1", "label": "Button 1", "x": 0.05, "y": 0.05, "w": 0.38, "h": 0.3},
            {"id": "button2", "label": "Button 2", "x": 0.55, "y": 0.05, "w": 0.38, "h": 0.3},
        ],
        "style": "classic",
        "image_file": "two_buttons.jpg",
        "prompt_hint": "Difficult choice between two options",
    },
    {
        "id": "galaxy-brain",
        "name": "Galaxy Brain",
        "description": "Expanding brain with 3-4 escalating ideas.",
        "zones": [
            {"id": "level1", "label": "Level 1 (small brain)", "x": 0.05, "y": 0.0, "w": 0.45, "h": 0.22},
            {"id": "level2", "label": "Level 2", "x": 0.05, "y": 0.25, "w": 0.45, "h": 0.22},
            {"id": "level3", "label": "Level 3", "x": 0.05, "y": 0.5, "w": 0.45, "h": 0.22},
            {"id": "level4", "label": "Level 4 (galaxy brain)", "x": 0.05, "y": 0.75, "w": 0.45, "h": 0.22},
        ],
        "style": "modern",
        "image_file": "galaxy_brain.jpg",
        "prompt_hint": "Escalating logic from dumb to 'genius'",
    },
    {
        "id": "chad",
        "name": "Chad vs Virgin / Yes Chad",
        "description": "Chad nodding confidently. One bold caption.",
        "zones": [
            {"id": "caption", "label": "Caption", "x": 0.05, "y": 0.75, "w": 0.9, "h": 0.2},
        ],
        "style": "classic",
        "image_file": "chad.jpg",
        "prompt_hint": "Confident agreement or alpha take",
    },
    {
        "id": "pepe-smug",
        "name": "Smug Pepe",
        "description": "Smug Pepe with top/bottom caption.",
        "zones": [
            {"id": "top", "label": "Top text", "x": 0.05, "y": 0.02, "w": 0.9, "h": 0.2},
            {"id": "bottom", "label": "Bottom text", "x": 0.05, "y": 0.78, "w": 0.9, "h": 0.2},
        ],
        "style": "classic",
        "image_file": "pepe_smug.png",
        "prompt_hint": "Smug observation or gotcha",
    },
    {
        "id": "stonks",
        "name": "Stonks",
        "description": "Meme man with chart. One caption.",
        "zones": [
            {"id": "caption", "label": "Caption", "x": 0.05, "y": 0.05, "w": 0.9, "h": 0.25},
        ],
        "style": "modern",
        "image_file": "stonks.jpg",
        "prompt_hint": "Ironic financial/profit take",
    },
    {
        "id": "guy-tapping-head",
        "name": "Guy Tapping Head",
        "description": "Big brain galaxy-level observation. Caption at bottom.",
        "zones": [
            {"id": "caption", "label": "Caption", "x": 0.05, "y": 0.65, "w": 0.9, "h": 0.3},
        ],
        "style": "classic",
        "image_file": "guy_tapping_head.jpg",
        "prompt_hint": "Unorthodox but logical take",
    },
]


def _registry_path() -> Path:
    return templates_dir() / _REGISTRY_FILE


def ensure_registry() -> None:
    """Seed the registry with default templates if it doesn't exist."""
    path = _registry_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(_DEFAULT_TEMPLATES, f, default_flow_style=False, allow_unicode=True)


def load_registry() -> list[dict]:
    ensure_registry()
    with open(_registry_path()) as f:
        data = yaml.safe_load(f) or []
    return data if isinstance(data, list) else []


def get_template(template_id: str) -> dict:
    registry = load_registry()
    for t in registry:
        if t["id"] == template_id:
            return t
    raise ValueError(
        f"Template '{template_id}' not found. "
        f"Available: {', '.join(t['id'] for t in registry)}"
    )


def get_template_image(template: dict) -> Optional[Path]:
    """Return path to template image or None if not downloaded."""
    img_file = template.get("image_file", "")
    path = templates_dir() / img_file
    return path if path.exists() else None


def validate_text_zones(template: dict, texts: dict) -> None:
    """Ensure all required zones have text."""
    for zone in template.get("zones", []):
        if zone["id"] not in texts:
            raise ValueError(
                f"Missing text for zone '{zone['id']}' ({zone['label']}) "
                f"in template '{template['id']}'"
            )
