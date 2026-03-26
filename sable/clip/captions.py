"""ASS subtitle generation from word-level timestamps."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


COLOR_MAP = {
    "white":  "&H00FFFFFF",
    "yellow": "&H0000FFFF",
    "black":  "&H00000000",
    "cyan":   "&H00FFFF00",
    "green":  "&H0000FF00",
    "red":    "&H000000FF",
}

# Maps base color name → ASS inline highlight color (&HBBGGRR)
HIGHLIGHT_PAIRS = {
    "yellow": "&H00FFFFFF",   # white
    "white":  "&H0000D7FF",   # gold (#FFD700 → BGR)
    "black":  "&H00FFFFFF",   # white
    "cyan":   "&H00FFFFFF",   # white
    "green":  "&H00FFFFFF",   # white
    "red":    "&H00FFFFFF",   # white
}


def _highlight_color(base: str) -> str:
    """Return ASS-format highlight color paired with the given base color."""
    return HIGHLIGHT_PAIRS.get(base, "&H00FFFFFF")


def _to_ass_color(color: str) -> str:
    """Convert named color or #RRGGBB hex to ASS &H00BBGGRR format."""
    if color in COLOR_MAP:
        return COLOR_MAP[color]
    if color.startswith("#") and len(color) == 7:
        r, g, b = color[1:3], color[3:5], color[5:7]
        return f"&H00{b}{g}{r}".upper()
    return COLOR_MAP["yellow"]


def _ass_header(color: str = "yellow") -> str:
    ass_color = _to_ass_color(color)
    return f"""\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,95,{ass_color},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,0,2,20,20,80,1

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


def _interpolate_words(segments: list[dict]) -> list[dict]:
    """Expand phrase-level segments into word-level via linear interpolation."""
    words = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = seg["start"]
        end = seg["end"]
        parts = text.split()
        if not parts:
            continue
        duration = (end - start) / len(parts)
        for i, word in enumerate(parts):
            words.append({
                "start": start + i * duration,
                "end":   start + (i + 1) * duration,
                "text":  word,
            })
    return words


def generate_word_captions(
    segments: list[dict],
    output_path: str | Path,
    style: str = "word",
    words_per_line: int = 3,
    color: str = "yellow",
    highlight_active: bool = True,
    position: str = "center",
) -> None:
    """
    Generate ASS subtitle file from word-level segments.

    style:
      - word: highlight one word at a time (karaoke effect when highlight_active=True)
      - phrase: group words_per_line words together
      - none: one segment per line

    position:
      - center: \\an5 (center of frame — default, used for stacked brainrot)
      - bottom: \\an2 (bottom-center — used for clip-only full 9:16)
    """
    output_path = Path(output_path)
    lines = [_ass_header(color)]

    if style == "word":
        word_segs = _interpolate_words(segments)
        if highlight_active:
            _gen_word_highlight_style(word_segs, lines, words_per_group=4,
                                      highlight_ass_color=_highlight_color(color),
                                      position=position)
        else:
            _gen_word_style(word_segs, lines, position=position)
    elif style == "phrase":
        _gen_phrase_style(segments, lines, words_per_line, position=position)
    else:
        _gen_segment_style(segments, lines, position=position)

    output_path.write_text("".join(lines))


def _gen_word_style(segments: list[dict], lines: list, position: str = "center") -> None:
    an = "2" if position == "bottom" else "5"
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = seg.get("start", 0)
        end = seg.get("end", start + 0.5)
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an{an}}}{text}\n")


def _gen_word_highlight_style(
    segments: list[dict],
    lines: list,
    words_per_group: int = 3,
    highlight_ass_color: str = "&H00FFFFFF",
    position: str = "center",
) -> None:
    """Karaoke-style: display a chunk of words, active word shown in highlight color."""
    an = "2" if position == "bottom" else "5"
    words = [s for s in segments if s.get("text", "").strip()]
    for i in range(0, len(words), words_per_group):
        chunk = words[i:i + words_per_group]
        if not chunk:
            continue
        chunk_texts = [w["text"].strip() for w in chunk]
        for j, word in enumerate(chunk):
            start = word["start"]
            end = word["end"]
            parts = []
            for k, text in enumerate(chunk_texts):
                if k == j:
                    parts.append(f"{{\\c{highlight_ass_color}}}{text}{{\\r}}")
                else:
                    parts.append(text)
            line_text = " ".join(parts)
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an{an}}}{line_text}\n")


def _gen_phrase_style(segments: list[dict], lines: list, n: int, position: str = "center") -> None:
    an = "2" if position == "bottom" else "5"
    words = [s for s in segments if s.get("text", "").strip()]
    for i in range(0, len(words), n):
        chunk = words[i:i + n]
        if not chunk:
            continue
        start = chunk[0]["start"]
        end = chunk[-1]["end"]
        text = " ".join(w["text"].strip() for w in chunk)
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an{an}}}{text}\n")


def _gen_segment_style(segments: list[dict], lines: list, position: str = "center") -> None:
    an = "2" if position == "bottom" else "5"
    # Group into natural sentences/pauses
    buffer: list[dict] = []
    for seg in segments:
        buffer.append(seg)
        text = seg.get("text", "")
        if any(p in text for p in (".", "?", "!", ",")) or not text.strip():
            if buffer:
                start = buffer[0]["start"]
                end = buffer[-1]["end"]
                text = " ".join(s.get("text", "").strip() for s in buffer).strip()
                if text:
                    lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an{an}}}{text}\n")
                buffer = []
    if buffer:
        start = buffer[0]["start"]
        end = buffer[-1]["end"]
        text = " ".join(s.get("text", "").strip() for s in buffer).strip()
        if text:
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an{an}}}{text}\n")
