"""Karaoke ASS subtitle generation for landscape 1280x720 explainer videos."""
from __future__ import annotations

from pathlib import Path


COLOR_MAP = {
    "white":  "&H00FFFFFF",
    "yellow": "&H0000FFFF",
    "black":  "&H00000000",
    "cyan":   "&H00FFFF00",
    "green":  "&H0000FF00",
    "red":    "&H000000FF",
}

HIGHLIGHT_PAIRS = {
    "yellow": "&H00FFFFFF",
    "white":  "&H0000D7FF",
    "black":  "&H00FFFFFF",
    "cyan":   "&H00FFFFFF",
    "green":  "&H00FFFFFF",
    "red":    "&H00FFFFFF",
}


def _to_ass_color(color: str) -> str:
    if color in COLOR_MAP:
        return COLOR_MAP[color]
    if color.startswith("#") and len(color) == 7:
        r, g, b = color[1:3], color[3:5], color[5:7]
        return f"&H00{b}{g}{r}".upper()
    return COLOR_MAP["yellow"]


def _highlight_color(base: str) -> str:
    return HIGHLIGHT_PAIRS.get(base, "&H00FFFFFF")


def _ass_header(color: str = "yellow", width: int = 1280, height: int = 720) -> str:
    ass_color = _to_ass_color(color)
    return f"""\
[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,55,{ass_color},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,20,20,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    """Convert seconds to ASS timestamp H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def generate_karaoke_ass(
    words: list[dict],
    output_path: str | Path,
    color: str = "yellow",
    words_per_group: int = 3,
    width: int = 1280,
    height: int = 720,
) -> None:
    """
    Generate a karaoke ASS subtitle file sized to the given canvas dimensions.

    words: list of {"start", "end", "text"} dicts (word-level timestamps)
    Displays up to words_per_group words at a time; active word highlighted.
    """
    output_path = Path(output_path)
    highlight = _highlight_color(color)
    lines = [_ass_header(color, width=width, height=height)]

    clean = [w for w in words if w.get("text", "").strip()]

    for i in range(0, len(clean), words_per_group):
        chunk = clean[i : i + words_per_group]
        if not chunk:
            continue
        chunk_texts = [w["text"].strip() for w in chunk]

        for j, word in enumerate(chunk):
            start = word["start"]
            end = word["end"]
            parts = []
            for k, text in enumerate(chunk_texts):
                if k == j:
                    parts.append(f"{{\\c{highlight}}}{text}{{\\r}}")
                else:
                    parts.append(text)
            line_text = " ".join(parts)
            lines.append(
                f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an2}}{line_text}\n"
            )

    output_path.write_text("".join(lines))
