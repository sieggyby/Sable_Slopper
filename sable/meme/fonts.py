"""Font resolution with fallback chain."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PIL import ImageFont

_FONT_SEARCH_DIRS = [
    Path.home() / ".sable" / "fonts",
    Path("/System/Library/Fonts"),
    Path("/Library/Fonts"),
    Path.home() / "Library" / "Fonts",
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
]

_IMPACT_NAMES = [
    "Impact.ttf", "impact.ttf",
    "Impact.otf",
]
_ARIAL_NAMES = [
    "Arial.ttf", "arial.ttf",
    "ArialMT.ttf",
    "LiberationSans-Regular.ttf",
    "DejaVuSans.ttf",
]
_BOLD_NAMES = [
    "Arial Bold.ttf", "Arial-Bold.ttf",
    "LiberationSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]


def _find_font(names: list[str]) -> Optional[Path]:
    for d in _FONT_SEARCH_DIRS:
        for name in names:
            candidate = d / name
            if candidate.exists():
                return candidate
    return None


def load_font(style: str = "classic", size: int = 60) -> ImageFont.FreeTypeFont:
    """
    Load a font for meme rendering.
    style: classic (Impact), modern (Arial Bold), minimal (Arial)
    Falls back gracefully to PIL default.
    """
    if style == "classic":
        names = _IMPACT_NAMES
    elif style in ("modern", "minimal"):
        names = _BOLD_NAMES + _ARIAL_NAMES
    else:
        names = _ARIAL_NAMES

    path = _find_font(names)
    if path:
        return ImageFont.truetype(str(path), size)

    # Try PIL's own font loader
    try:
        return ImageFont.truetype("Impact", size)
    except (IOError, OSError):
        pass
    try:
        return ImageFont.truetype("Arial", size)
    except (IOError, OSError):
        pass

    # Last resort: default bitmap font (very small, no size control)
    return ImageFont.load_default()  # type: ignore[return-value]


def find_font_size(
    draw,
    text: str,
    max_width: int,
    max_height: int,
    style: str = "classic",
    start_size: int = 80,
    min_size: int = 20,
) -> tuple[ImageFont.FreeTypeFont, int]:
    """Binary-search for the largest font size that fits within bounds."""
    lo, hi = min_size, start_size
    best_font = load_font(style, min_size)
    best_size = min_size

    for size in range(hi, lo - 1, -2):
        font = load_font(style, size)
        bbox = draw.multiline_textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= max_width and h <= max_height:
            return font, size

    return best_font, best_size
