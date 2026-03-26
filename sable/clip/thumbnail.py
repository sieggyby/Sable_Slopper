"""Generate a colorful 1280×720 thumbnail PNG with a Claude-written headline."""
from __future__ import annotations

import asyncio
import base64
import html
import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

PALETTES = {
    "red":    [(220, 40,  40),  (120, 10,  10)],
    "blue":   [(30,  100, 220), (10,  40,  120)],
    "green":  [(30,  180, 80),  (10,  80,  30)],
    "orange": [(240, 120, 20),  (160, 60,  10)],
    "purple": [(140, 40,  200), (60,  10,  100)],
    "teal":   [(20,  180, 170), (10,  80,  80)],
}

_PALETTE_NAMES = list(PALETTES.keys())

FACE_W = 768  # left panel width for face (PIL fallback)

_HTML_TEMPLATE = """\
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    width:1280px; height:720px; overflow:hidden;
    position:relative;
    font-family:'Arial Black',Impact,'Helvetica Neue',sans-serif;
    background:#0a0a0a;
}}
.bg {{
    position:absolute; inset:0;
    background-image:url('{bg_data_uri}');
    background-size:cover;
    background-position:center top;
}}
.gradient-overlay {{
    position:absolute; inset:0;
    background:linear-gradient(
        {gradient_dir},
        rgba(0,0,0,0.88) 0%,
        rgba(0,0,0,0.78) 20%,
        rgba(0,0,0,0.50) 38%,
        rgba(0,0,0,0.10) 55%,
        rgba(0,0,0,0.00) 68%
    );
}}
.color-tint {{
    position:absolute; inset:0;
    background:rgba({tint_r},{tint_g},{tint_b},0.16);
    mix-blend-mode:screen;
}}
.text-zone {{
    position:absolute; {text_zone_side}:48px; top:0; bottom:8px; width:620px;
    display:flex; flex-direction:column; justify-content:center;
}}
.headline {{
    color:#ffffff;
    font-size:{font_size}px;
    font-weight:900;
    line-height:1.12;
    letter-spacing:-0.02em;
    text-transform:uppercase;
    text-shadow:
        3px 3px 0px rgba(0,0,0,0.95),
        -2px -2px 0px rgba(0,0,0,0.85),
        6px 6px 18px rgba(0,0,0,0.9),
        0 0 40px rgba(0,0,0,0.6);
    word-break:break-word;
}}
.accent-bar {{
    position:absolute; bottom:0; left:0; right:0;
    height:8px;
    background:rgb({accent_r},{accent_g},{accent_b});
}}
</style></head><body>
<div class="bg"></div>
<div class="gradient-overlay"></div>
<div class="color-tint"></div>
<div class="text-zone"><div class="headline">{headline}</div></div>
<div class="accent-bar"></div>
</body></html>"""


def _get_headline_and_palette(hint: str) -> tuple[str, str]:
    """Ask Claude for a 4–6 word headline and a palette name."""
    from sable.shared.api import call_claude_json

    prompt = (
        "Given this clip text, write a punchy 4-6 word headline (plain English, "
        "5th-grader readable, no hashtags, no quotes) and choose a background color.\n\n"
        f"Clip text: {hint or 'crypto community discussion'}\n\n"
        'Return JSON: {"headline": "...", "palette": "<red|blue|green|orange|purple|teal>"}'
    )
    raw = call_claude_json(prompt, max_tokens=256)  # budget-exempt: thumbnail generation has no org context
    try:
        data = json.loads(raw)
        headline = str(data.get("headline", "Something Big Is Coming")).strip()
        palette = data.get("palette", "blue")
        if palette not in PALETTES:
            palette = "blue"
        return headline, palette
    except Exception:
        return "Something Big Is Coming", "blue"


def _load_font(size: int):
    from PIL import ImageFont
    for name in ["Impact", "DejaVuSans-Bold", "DejaVu Sans Bold"]:
        try:
            return ImageFont.truetype(name, size)
        except (IOError, OSError):
            pass
    for path in [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/Library/Fonts/Impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except (IOError, OSError):
                pass
    return ImageFont.load_default()


def _make_gradient(width: int, height: int, top_rgb: tuple, bottom_rgb: tuple):
    from PIL import Image
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    assert pixels is not None
    for y in range(height):
        t = y / (height - 1)
        r = int(top_rgb[0] + (bottom_rgb[0] - top_rgb[0]) * t)
        g = int(top_rgb[1] + (bottom_rgb[1] - top_rgb[1]) * t)
        b = int(top_rgb[2] + (bottom_rgb[2] - top_rgb[2]) * t)
        for x in range(width):
            pixels[x, y] = (r, g, b)
    return img


def _draw_headline_centered(draw, headline: str, zone_x: int, zone_w: int, canvas_h: int):
    """Draw headline centered within a horizontal zone."""
    for font_size in range(160, 40, -10):
        font = _load_font(font_size)
        words = headline.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > zone_w * 0.88 and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)

        line_h = draw.textbbox((0, 0), "Ag", font=font)[3] + 10
        total_h = line_h * len(lines)
        if total_h < canvas_h * 0.72:
            break

    y = (canvas_h - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = zone_x + (zone_w - text_w) // 2
        for dx in range(-6, 7, 2):
            for dy in range(-6, 7, 2):
                if dx or dy:
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_h


def _draw_accent_bar(img, top_rgb: tuple):
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    W, H = img.size
    bar_h = 8
    accent = tuple(min(255, int(c * 1.3)) for c in top_rgb)
    draw.rectangle([(0, H - bar_h), (W, H)], fill=accent)


def _extract_candidate_frames(
    source_video: Path, start: float, end: float,
    tmp_dir: Path, n: int = 8,
) -> list[Path]:
    """Extract ~n evenly-spaced frames from the clip window."""
    try:
        from sable.shared.ffmpeg import require_ffmpeg
        import subprocess

        ffmpeg = require_ffmpeg()
        duration = end - start
        if duration <= 0:
            return []

        fps = n / duration
        fps = max(0.2, min(2.0, fps))

        out_pattern = str(tmp_dir / "thumb_%04d.png")
        subprocess.run(
            [
                ffmpeg,
                "-ss", str(start),
                "-i", str(source_video),
                "-t", str(duration),
                "-vf", f"fps={fps}",
                "-frames:v", str(n),
                out_pattern,
            ],
            capture_output=True,
            check=True,
        )
        frames = sorted(tmp_dir.glob("thumb_*.png"))
        return frames
    except Exception:
        return []


def _pick_best_frame(frames: list[Path]) -> tuple[Path, tuple | None]:
    """Return (best_frame_path, face_location_or_None)."""
    try:
        import face_recognition
        import numpy as np
        from PIL import Image
    except ImportError:
        # No face_recognition — fall back to contrast-based selection
        return _pick_by_contrast(frames), None

    best_frame = frames[0]
    best_face = None
    best_score = -1

    for frame_path in frames:
        try:
            arr = np.array(Image.open(frame_path).convert("RGB"))
            locs = face_recognition.face_locations(arr, model="hog")

            if not locs:
                continue

            h, w = arr.shape[:2]
            for loc in locs:
                top, right, bottom, left = loc
                area = (right - left) * (bottom - top)
                y_center = (top + bottom) / 2

                score = area
                # Prefer face in upper 60% of frame
                if y_center < h * 0.6:
                    score *= 1.2
                # Penalize multi-person frames
                if len(locs) > 2:
                    score *= 0.5

                if score > best_score:
                    best_score = score
                    best_frame = frame_path
                    best_face = loc
        except Exception:
            continue

    if best_face is not None:
        return best_frame, best_face

    # No faces found anywhere — pick by contrast
    return _pick_by_contrast(frames), None


def _pick_by_contrast(frames: list[Path]) -> Path:
    """Return the frame with highest local contrast (most visually dynamic)."""
    try:
        from PIL import Image, ImageFilter
        import numpy as np

        best_frame = frames[0]
        best_contrast = -1.0

        for frame_path in frames:
            try:
                img = Image.open(frame_path).convert("L")
                edges = img.filter(ImageFilter.FIND_EDGES)
                contrast = float(np.array(edges).mean())
                if contrast > best_contrast:
                    best_contrast = contrast
                    best_frame = frame_path
            except Exception:
                continue

        return best_frame
    except Exception:
        return frames[0]


def _crop_face_portrait(
    frame_path: Path,
    face_loc: tuple | None,
    target_w: int,
    target_h: int,
):
    """Crop frame around face (or center-crop) and resize to target dimensions."""
    from PIL import Image, ImageEnhance

    img = Image.open(frame_path).convert("RGB")
    iw, ih = img.size

    if face_loc is not None:
        top, right, bottom, left = face_loc
        fw = right - left
        fh = bottom - top

        # Expand bounding box by 80% in all directions
        pad_x = int(fw * 0.8)
        pad_y = int(fh * 0.8)

        cx = (left + right) // 2
        cy = (top + bottom) // 2

        x0 = max(0, cx - fw // 2 - pad_x)
        x1 = min(iw, cx + fw // 2 + pad_x)
        y0 = max(0, cy - fh // 2 - pad_y)
        y1 = min(ih, cy + fh // 2 + pad_y)

        cropped = img.crop((x0, y0, x1, y1))
    else:
        # Center-crop to target aspect ratio
        target_ratio = target_w / target_h
        src_ratio = iw / ih
        if src_ratio > target_ratio:
            new_w = int(ih * target_ratio)
            x0 = (iw - new_w) // 2
            cropped = img.crop((x0, 0, x0 + new_w, ih))
        else:
            new_h = int(iw / target_ratio)
            y0 = (ih - new_h) // 2
            cropped = img.crop((0, y0, iw, y0 + new_h))

    resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
    enhanced = ImageEnhance.Contrast(resized).enhance(1.15)
    return enhanced


def _compose_split(
    face_img,
    headline: str,
    top_rgb: tuple,
    bottom_rgb: tuple,
    canvas_w: int = 1280,
    canvas_h: int = 720,
    blend_zone: int = 80,
    text_left: bool = False,
):
    """Compose face + gradient+text panels with alpha-fade seam.

    text_left=False (default): face on left, text on right.
    text_left=True: face on right, text on left (face is on left side of source frame).
    """
    from PIL import Image, ImageDraw

    # Full gradient as base
    canvas = _make_gradient(canvas_w, canvas_h, top_rgb, bottom_rgb)

    if text_left:
        # Face on right: paste at x = canvas_w - FACE_W
        face_x = canvas_w - FACE_W
        # Build seam mask: ramps from 0 at left edge to 255 (opaque) on right
        mask = Image.new("L", (FACE_W, canvas_h), 255)
        mask_pixels = mask.load()
        assert mask_pixels is not None
        for x in range(blend_zone):
            alpha = int(255 * (x / blend_zone))
            for y in range(canvas_h):
                mask_pixels[x, y] = alpha
        canvas.paste(face_img, (face_x, 0), mask=mask)
        # Text on left panel
        draw = ImageDraw.Draw(canvas)
        _draw_headline_centered(draw, headline, 0, canvas_w - FACE_W, canvas_h)
    else:
        # Face on left: paste at x = 0
        mask = Image.new("L", (FACE_W, canvas_h), 255)
        mask_pixels = mask.load()
        assert mask_pixels is not None
        blend_start = FACE_W - blend_zone
        for x in range(blend_start, FACE_W):
            alpha = int(255 * (1.0 - (x - blend_start) / blend_zone))
            for y in range(canvas_h):
                mask_pixels[x, y] = alpha
        canvas.paste(face_img, (0, 0), mask=mask)
        # Text on right panel
        draw = ImageDraw.Draw(canvas)
        _draw_headline_centered(draw, headline, FACE_W, canvas_w - FACE_W, canvas_h)

    return canvas


# ---------------------------------------------------------------------------
# Playwright HTML compositor
# ---------------------------------------------------------------------------

def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _font_size_for_headline(headline: str) -> int:
    word_count = len(headline.split())
    if word_count <= 2:
        return 120
    elif word_count == 3:
        return 100
    elif word_count == 4:
        return 86
    else:
        return 72


async def _render_html_to_png_async(html_content: str, output_path: Path) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
        )
        await page.set_content(html_content, wait_until="domcontentloaded")
        await page.wait_for_timeout(80)
        await page.screenshot(
            path=str(output_path),
            type="png",
            clip={"x": 0, "y": 0, "width": 1280, "height": 720},
        )
        await browser.close()


def _render_html_to_png(html_content: str, output_path: Path) -> None:
    coro = _render_html_to_png_async(html_content, output_path)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Nested event loop (Click/Jupyter) — run in a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            future.result()
    else:
        asyncio.run(coro)


def _compose_playwright(
    frame_path: Path,
    headline: str,
    top_rgb: tuple,
    output_path: Path,
    face_on_left: bool = False,
) -> bool:
    """Render full-bleed HTML thumbnail. Returns True on success."""
    try:
        img_bytes = frame_path.read_bytes()
        b64 = base64.b64encode(img_bytes).decode("ascii")
        bg_data_uri = f"data:image/png;base64,{b64}"

        accent = tuple(min(255, int(c * 1.3)) for c in top_rgb)
        escaped_headline = html.escape(headline)
        font_size = _font_size_for_headline(headline)

        gradient_dir   = "to left"  if face_on_left else "to right"
        text_zone_side = "right"    if face_on_left else "left"

        rendered = _HTML_TEMPLATE.format(
            bg_data_uri=bg_data_uri,
            tint_r=top_rgb[0], tint_g=top_rgb[1], tint_b=top_rgb[2],
            font_size=font_size,
            accent_r=accent[0], accent_g=accent[1], accent_b=accent[2],
            headline=escaped_headline,
            gradient_dir=gradient_dir,
            text_zone_side=text_zone_side,
        )

        _render_html_to_png(rendered, output_path)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_thumbnail(
    headline_hint: str,
    output_path: Path,
    source_video: Optional[Path] = None,
    clip_start: float = 0.0,
    clip_end: float = 0.0,
    accent_color: Optional[str] = None,
) -> Path:
    """
    Generate a 1280×720 thumbnail PNG.

    Fallback chain:
      1. Video frame + Playwright → HTML compositor (full-bleed photo, CSS gradient)
      2. Video frame + no Playwright → PIL split-panel
      3. No video frame → PIL gradient-only
      4. Any exception → PIL gradient-only
    """
    headline, palette_name = _get_headline_and_palette(headline_hint)
    if accent_color and accent_color in PALETTES:
        palette_name = accent_color

    top_rgb, bottom_rgb = PALETTES[palette_name]
    W, H = 1280, 720

    best_frame: Optional[Path] = None
    face_img = None
    face_on_left = False

    if source_video and Path(source_video).exists() and clip_end > clip_start:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                frames = _extract_candidate_frames(
                    Path(source_video), clip_start, clip_end, Path(tmp)
                )
                if frames:
                    best_frame_tmp, face_loc = _pick_best_frame(frames)
                    face_img = _crop_face_portrait(best_frame_tmp, face_loc, FACE_W, H)
                    # Detect which side the face is on
                    if face_loc is not None:
                        from PIL import Image as _PImage
                        _fw = _PImage.open(best_frame_tmp).width
                        face_center_x = (face_loc[1] + face_loc[3]) / 2  # (right + left) / 2
                        face_on_left = face_center_x < _fw / 2
                    # Copy frame out before tempdir evaporates
                    kept = Path(output_path).with_suffix(".thumb_frame.png")
                    shutil.copy2(best_frame_tmp, kept)
                    best_frame = kept
        except Exception:
            best_frame = None
            face_img = None
            face_on_left = False

    # Try Playwright first
    playwright_ok = False
    if best_frame is not None and _playwright_available():
        playwright_ok = _compose_playwright(best_frame, headline, top_rgb, Path(output_path),
                                            face_on_left=face_on_left)

    # Clean up temp frame regardless of path taken
    if best_frame is not None and best_frame.exists():
        best_frame.unlink(missing_ok=True)

    if not playwright_ok:
        from PIL import ImageDraw
        if face_img is not None:
            img = _compose_split(face_img, headline, top_rgb, bottom_rgb, text_left=face_on_left)
        else:
            img = _make_gradient(W, H, top_rgb, bottom_rgb)
            _draw_headline_centered(ImageDraw.Draw(img), headline, 0, W, H)
        _draw_accent_bar(img, top_rgb)
        output_path = Path(output_path)
        img.save(output_path, "PNG")

    return Path(output_path)
