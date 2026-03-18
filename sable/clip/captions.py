"""ASS subtitle generation from word-level timestamps."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,20,20,80,1

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


def generate_word_captions(
    segments: list[dict],
    output_path: str | Path,
    style: str = "word",
    words_per_line: int = 3,
) -> None:
    """
    Generate ASS subtitle file from word-level segments.

    style:
      - word: highlight one word at a time
      - phrase: group words_per_line words together
      - none: one segment per line
    """
    output_path = Path(output_path)
    lines = [_ASS_HEADER]

    if style == "word":
        _gen_word_style(segments, lines)
    elif style == "phrase":
        _gen_phrase_style(segments, lines, words_per_line)
    else:
        _gen_segment_style(segments, lines)

    output_path.write_text("".join(lines))


def _gen_word_style(segments: list[dict], lines: list) -> None:
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = seg.get("start", 0)
        end = seg.get("end", start + 0.5)
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an5}}{text}\n")


def _gen_phrase_style(segments: list[dict], lines: list, n: int) -> None:
    words = [s for s in segments if s.get("text", "").strip()]
    for i in range(0, len(words), n):
        chunk = words[i:i + n]
        if not chunk:
            continue
        start = chunk[0]["start"]
        end = chunk[-1]["end"]
        text = " ".join(w["text"].strip() for w in chunk)
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an5}}{text}\n")


def _gen_segment_style(segments: list[dict], lines: list) -> None:
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
                    lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an5}}{text}\n")
                buffer = []
    if buffer:
        start = buffer[0]["start"]
        end = buffer[-1]["end"]
        text = " ".join(s.get("text", "").strip() for s in buffer).strip()
        if text:
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{{\\an5}}{text}\n")
