"""Thumbnail generators for the character explainer pipeline.

Two methods:
  - generate_character_thumbnail: character open-mouth PNG on gradient background
  - generate_photo_thumbnail: supplied photo with title overlay and vignette
Canvas is 1200×1200 (Twitter square).
"""
from __future__ import annotations

from pathlib import Path

from sable.clip.thumbnail import (
    PALETTES,
    _draw_accent_bar,
    _load_font,
    _make_gradient,
)
from sable.character_explainer.config import CharacterProfile

CANVAS = (1200, 1200)


def generate_character_thumbnail(
    character: CharacterProfile,
    topic: str,
    output_path: Path,
    palette_name: str = "orange",
) -> Path:
    """
    Method 1: Character open-mouth PNG on flashy gradient background + topic title.

    Layout:
    - Full-canvas gradient background
    - Character PNG (RGBA) scaled to fill right ~72% of canvas, anchored bottom-right
    - Topic title in Impact, white + black outline, left zone upper area
    - 10px accent bar at bottom
    """
    from PIL import Image, ImageDraw

    W, H = CANVAS
    if palette_name not in PALETTES:
        palette_name = "orange"
    top_rgb, bottom_rgb = PALETTES[palette_name]

    canvas = _make_gradient(W, H, top_rgb, bottom_rgb).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # Paste character PNG if available
    if character.image_open_mouth:
        char_path = Path(character.image_open_mouth).expanduser()
        if char_path.exists():
            char_img = Image.open(char_path).convert("RGBA")
            cw, ch = char_img.size
            # Scale by height to 1200px, then check if width is reasonable
            scale = H / ch
            scaled_w = int(cw * scale)
            scaled_h = H
            char_img = char_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
            # Anchor bottom-right with a slight bleed
            paste_x = W - scaled_w + 20
            paste_y = 0
            canvas.paste(char_img, (paste_x, paste_y), mask=char_img.split()[3])

    # Draw title in left 55%, upper 60% of canvas
    title = topic.upper()
    title_zone_w = int(W * 0.55)
    title_zone_h = int(H * 0.60)

    # Find best font size that fits
    for font_size in range(160, 40, -10):
        font = _load_font(font_size)
        words = title.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > title_zone_w * 0.88 and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)

        line_h = draw.textbbox((0, 0), "Ag", font=font)[3] + 14
        total_h = line_h * len(lines)
        if total_h < title_zone_h * 0.85:
            break

    # Center text block in upper 60% of canvas
    y = (title_zone_h - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (title_zone_w - text_w) // 2
        # Outline
        for dx in range(-6, 7, 2):
            for dy in range(-6, 7, 2):
                if dx or dy:
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    canvas_rgb = canvas.convert("RGB")
    _draw_accent_bar(canvas_rgb, top_rgb)
    output_path = Path(output_path)
    canvas_rgb.save(output_path, "PNG")
    return output_path


def generate_photo_thumbnail(
    photo_path: Path,
    topic: str,
    output_path: Path,
) -> Path:
    """
    Method 2: Supplied photo fills canvas; title text overlaid with vignette.

    Layout:
    - Photo scaled/center-cropped to 1200×1200
    - Radial vignette darkens corners ~50%
    - Bottom gradient fade (y=700→1200, black 0%→60%) for text readability
    - Topic title in Impact, bottom-left zone, white + outline
    - 10px accent bar in dominant saturated color from bottom-center of photo
    """
    from PIL import Image, ImageDraw, ImageFilter
    import colorsys

    W, H = CANVAS
    photo = Image.open(photo_path).convert("RGB")
    pw, ph = photo.size

    # Center-crop to square then resize
    if pw > ph:
        x0 = (pw - ph) // 2
        photo = photo.crop((x0, 0, x0 + ph, ph))
    elif ph > pw:
        y0 = (ph - pw) // 2
        photo = photo.crop((0, y0, pw, y0 + pw))
    photo = photo.resize((W, H), Image.Resampling.LANCZOS)

    canvas = photo.copy().convert("RGBA")

    # Radial vignette — darken corners by ~50%
    vignette = Image.new("L", (W, H), 0)
    v_pixels = vignette.load()
    assert v_pixels is not None
    cx, cy = W // 2, H // 2
    max_dist = (cx**2 + cy**2) ** 0.5
    for y in range(H):
        for x in range(W):
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            t = min(1.0, dist / max_dist)
            # Alpha 0 at center (no darkening), up to 128 at corners (50% dark)
            v_pixels[x, y] = int(t ** 1.5 * 128)
    dark_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark_layer.putalpha(vignette)
    canvas = Image.alpha_composite(canvas, dark_layer)

    # Bottom gradient fade y=700→1200, black 0%→60%
    grad_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_pixels = grad_layer.load()
    assert g_pixels is not None
    grad_start = 700
    for y in range(grad_start, H):
        t = (y - grad_start) / (H - grad_start)
        alpha = int(t * 153)  # 60% of 255
        for x in range(W):
            g_pixels[x, y] = (0, 0, 0, alpha)
    canvas = Image.alpha_composite(canvas, grad_layer)

    canvas_rgb = canvas.convert("RGB")
    draw = ImageDraw.Draw(canvas_rgb)

    # Sample bottom-center strip for dominant saturated color
    strip = canvas_rgb.crop((W // 4, H - 80, 3 * W // 4, H - 10))
    accent_rgb = _dominant_saturated_color(strip)

    # Draw title text: bottom-left zone, auto-fit font size 130→80px
    title = topic.upper()
    text_x = 60
    text_y_max = H - 80  # leave room for accent bar + padding

    for font_size in range(130, 50, -10):
        font = _load_font(font_size)
        words = title.split()
        lines: list[str] = []
        current = ""
        max_w = int(W * 0.85)
        for word in words:
            test = (current + " " + word).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_w and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)

        line_h: int = int(draw.textbbox((0, 0), "Ag", font=font)[3]) + 10
        total_h = line_h * len(lines)
        # Must fit between y=700 and y=text_y_max
        if total_h < (text_y_max - 700):
            break

    # Draw from bottom up
    y = text_y_max - total_h
    for line in lines:
        for dx in range(-5, 6, 2):
            for dy in range(-5, 6, 2):
                if dx or dy:
                    draw.text((text_x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((text_x, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    # Accent bar using dominant color
    bar_h = 10
    draw.rectangle([(0, H - bar_h), (W, H)], fill=accent_rgb)

    output_path = Path(output_path)
    canvas_rgb.save(output_path, "PNG")
    return output_path


def _dominant_saturated_color(img) -> tuple[int, int, int]:
    """Sample pixels and return the most saturated color found."""
    import colorsys

    img_small = img.resize((20, 20))
    pixels = list(img_small.getdata())
    best_color = (255, 165, 0)  # fallback orange
    best_sat = -1.0
    for r, g, b in pixels:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > best_sat and v > 0.2:
            best_sat = s
            best_color = (r, g, b)
    return best_color
