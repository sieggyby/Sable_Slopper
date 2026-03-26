"""Pillow meme rendering with auto font-sizing, word-wrap, outlines."""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from sable.meme.fonts import load_font, find_font_size
from sable.meme.templates import get_template, get_template_image


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw, max_width: int) -> str:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current: list[str] = []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple = (255, 255, 255),
    outline: tuple = (0, 0, 0),
    outline_width: int = 3,
    align: str = "center",
) -> None:
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.multiline_text((x + dx, y + dy), text, font=font, fill=outline, align=align)
    draw.multiline_text(pos, text, font=font, fill=fill, align=align)


def _draw_shadow_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple = (255, 255, 255),
    shadow_offset: int = 3,
    align: str = "center",
) -> None:
    x, y = pos
    shadow = (0, 0, 0, 180)
    draw.multiline_text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow, align=align)
    draw.multiline_text(pos, text, font=font, fill=fill, align=align)


def render_meme(
    template_id: str,
    texts: dict[str, str],
    output_path: str | Path,
    style: Optional[str] = None,
) -> Path:
    """
    Render a meme to a PNG file.

    texts: {zone_id: text_string}
    style: classic | modern | minimal (overrides template default)
    """
    template = get_template(template_id)
    img_path = get_template_image(template)
    render_style = style or template.get("style", "classic")

    if img_path:
        img = Image.open(str(img_path)).convert("RGBA")
    else:
        # Generate a placeholder image
        img = _placeholder_image(template)

    draw = ImageDraw.Draw(img)
    width, height = img.size

    for zone in template.get("zones", []):
        zone_id = zone["id"]
        text = texts.get(zone_id, "")
        if not text:
            continue

        # Zone bounds in pixels
        zx = int(zone["x"] * width)
        zy = int(zone["y"] * height)
        zw = int(zone["w"] * width)
        zh = int(zone["h"] * height)

        # Find best font size
        font, size = find_font_size(
            draw, text, zw - 8, zh - 8,
            style=render_style, start_size=72, min_size=16
        )

        # Wrap text
        wrapped = _wrap_text(text, font, draw, zw - 8)
        # Re-check size after wrapping
        font, _ = find_font_size(draw, wrapped, zw - 8, zh - 8, style=render_style, start_size=size)

        # Compute text bbox for centering
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = zx + (zw - tw) // 2
        ty = zy + (zh - th) // 2

        pos = (int(tx), int(ty))
        if render_style == "classic":
            _draw_outlined_text(draw, pos, wrapped, font, outline_width=3)
        elif render_style == "modern":
            _draw_outlined_text(draw, pos, wrapped, font,
                                fill=(30, 30, 30), outline=(220, 220, 220), outline_width=1)
        else:  # minimal
            _draw_shadow_text(draw, pos, wrapped, font)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save as PNG (convert RGBA → RGB for JPEG compatibility)
    if output_path.suffix.lower() in (".jpg", ".jpeg"):
        img = img.convert("RGB")
    img.save(str(output_path))

    return output_path


def _placeholder_image(template: dict) -> Image.Image:
    """Create a placeholder gray image with template name."""
    img = Image.new("RGBA", (800, 600), color=(100, 100, 100, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = load_font("classic", 40)
    except Exception:
        font = ImageFont.load_default()  # type: ignore[assignment]
    draw.text((400, 300), f"[{template['name']}]", font=font, fill=(200, 200, 200), anchor="mm")
    return img
