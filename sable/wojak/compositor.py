"""Pillow multi-layer scene compositor for wojak scenes."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from sable.meme.fonts import load_font
from sable.shared.paths import account_output_dir, wojaks_dir
from sable.wojak.library import get_wojak, get_wojak_image


# Canvas dimensions
CANVAS_W = 900
CANVAS_H = 600
LABEL_FONT_SIZE = 22
CAPTION_FONT_SIZE = 28

# Position slots: (x_offset_fraction, y_offset_fraction, width_fraction)
# These are normalized [0..1] relative to canvas
_POSITION_SLOTS: dict[str, dict] = {
    "left":       {"x": 0.02,  "y": 0.10, "w": 0.40, "h": 0.75},
    "right":      {"x": 0.58,  "y": 0.10, "w": 0.40, "h": 0.75},
    "center":     {"x": 0.25,  "y": 0.10, "w": 0.50, "h": 0.75},
    "top-left":   {"x": 0.02,  "y": 0.02, "w": 0.40, "h": 0.55},
    "top-right":  {"x": 0.58,  "y": 0.02, "w": 0.40, "h": 0.55},
    "bottom-left":{"x": 0.02,  "y": 0.45, "w": 0.40, "h": 0.50},
    "bottom-right":{"x": 0.58, "y": 0.45, "w": 0.40, "h": 0.50},
}

VALID_POSITIONS = list(_POSITION_SLOTS.keys())


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple = (20, 20, 20),
    outline: tuple = (255, 255, 255),
    outline_width: int = 2,
    align: str = "center",
) -> None:
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.multiline_text((x + dx, y + dy), text, font=font, fill=outline, align=align)
    draw.multiline_text(pos, text, font=font, fill=fill, align=align)


def _fit_wojak(img: Image.Image, slot_w: int, slot_h: int) -> Image.Image:
    """Scale wojak to fit within slot, preserving aspect ratio."""
    orig_w, orig_h = img.size
    scale = min(slot_w / orig_w, slot_h / orig_h, 1.0)
    new_w = max(1, int(orig_w * scale))
    new_h = max(1, int(orig_h * scale))
    return img.resize((new_w, new_h), Image.LANCZOS)


def render_scene(
    layers: list[dict],
    caption: str,
    output_path: Path,
    bg_color: tuple = (235, 235, 235),
) -> Path:
    """
    Composite multiple wojak PNG layers into a single scene image.

    layers: [{"wojak_id": str, "position": str, "label": str}, ...]
    caption: optional top/bottom caption text
    output_path: destination PNG path
    bg_color: RGB background color
    """
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (*bg_color, 255))
    draw = ImageDraw.Draw(canvas)

    try:
        label_font = load_font("modern", LABEL_FONT_SIZE)
    except Exception:
        label_font = ImageFont.load_default()

    try:
        caption_font = load_font("modern", CAPTION_FONT_SIZE)
    except Exception:
        caption_font = label_font

    for layer in layers:
        wojak_id = layer["wojak_id"]
        position = layer.get("position", "center")
        label = layer.get("label", "")

        if position not in _POSITION_SLOTS:
            raise ValueError(
                f"Invalid position '{position}'. Valid: {', '.join(VALID_POSITIONS)}"
            )

        slot = _POSITION_SLOTS[position]
        slot_x = int(slot["x"] * CANVAS_W)
        slot_y = int(slot["y"] * CANVAS_H)
        slot_w = int(slot["w"] * CANVAS_W)
        slot_h = int(slot["h"] * CANVAS_H)

        # Reserve bottom of slot for label text
        label_reserve = 30 if label else 0
        img_slot_h = slot_h - label_reserve

        wojak = get_wojak(wojak_id)
        img_path = get_wojak_image(wojak)

        if img_path:
            woj_img = Image.open(str(img_path)).convert("RGBA")
            woj_img = _fit_wojak(woj_img, slot_w, img_slot_h)
            # Center horizontally within slot
            paste_x = slot_x + (slot_w - woj_img.width) // 2
            paste_y = slot_y
            canvas.alpha_composite(woj_img, (paste_x, paste_y))
        else:
            # Placeholder box
            box_x1, box_y1 = slot_x + 4, slot_y + 4
            box_x2, box_y2 = slot_x + slot_w - 4, slot_y + img_slot_h - 4
            draw.rectangle([box_x1, box_y1, box_x2, box_y2], fill=(180, 180, 180, 200))
            draw.text(
                (slot_x + slot_w // 2, slot_y + img_slot_h // 2),
                f"[{wojak_id}]",
                font=label_font,
                fill=(80, 80, 80),
                anchor="mm",
            )

        # Draw label below the wojak image
        if label:
            label_y = slot_y + img_slot_h + 2
            label_x = slot_x + slot_w // 2
            _draw_outlined_text(
                draw,
                (label_x, label_y),
                label,
                label_font,
                align="center",
            )

    # Draw caption at top if provided
    if caption:
        cap_x = CANVAS_W // 2
        cap_y = 8
        _draw_outlined_text(
            draw,
            (cap_x, cap_y),
            caption,
            caption_font,
            align="center",
        )

    # Save output
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final = canvas.convert("RGB")
    final.save(str(output_path), format="PNG")

    return output_path


def scene_output_path(handle: str, filename: str) -> Path:
    """Return output path for a wojak scene image."""
    d = account_output_dir(handle) / "wojak_scenes"
    d.mkdir(parents=True, exist_ok=True)
    return d / filename
