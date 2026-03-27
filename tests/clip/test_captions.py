"""Tests for sable.clip.captions — ASS generation, color conversion, timestamps."""
import pytest


def test_to_ass_color_hex_swaps_r_and_b():
    from sable.clip.captions import _to_ass_color

    # #FF8040: R=FF, G=80, B=40 → BGR ASS = &H00{40}{80}{FF} = &H004080FF
    result = _to_ass_color("#FF8040")
    assert result == "&H004080FF"


@pytest.mark.parametrize("seconds,expected", [
    (0.0,    "0:00:00.00"),
    (3661.5, "1:01:01.50"),
    (90.50,  "0:01:30.50"),
])
def test_ts_converts_seconds_to_ass_format(seconds, expected):
    from sable.clip.captions import _ts

    assert _ts(seconds) == expected


def test_interpolate_words_uniform_distribution():
    from sable.clip.captions import _interpolate_words

    segments = [{"start": 0.0, "end": 1.0, "text": "hello world"}]
    words = _interpolate_words(segments)

    assert len(words) == 2
    assert words[0]["start"] == 0.0
    assert words[0]["end"] == pytest.approx(0.5)
    assert words[1]["start"] == pytest.approx(0.5)
    assert words[1]["end"] == pytest.approx(1.0)


def test_generate_word_captions_bottom_position_uses_an2(tmp_path):
    from sable.clip.captions import generate_word_captions

    segments = [{"start": 0.0, "end": 2.0, "text": "hello world"}]
    out = tmp_path / "test.ass"
    generate_word_captions(segments, out, style="word", position="bottom")

    content = out.read_text()
    assert r"\an2" in content
    assert r"\an5" not in content


def test_generate_word_captions_highlight_active_wraps_current_word(tmp_path):
    from sable.clip.captions import generate_word_captions

    segments = [{"start": 0.0, "end": 2.0, "text": "hello world"}]
    out = tmp_path / "test.ass"
    generate_word_captions(segments, out, style="word", highlight_active=True)

    content = out.read_text()
    assert r"\c&H" in content
    assert r"{\r}" in content


def test_generate_word_captions_offset_segments_filtered(tmp_path):
    """Assembler offsets segment timestamps to clip-relative before calling captions.

    Simulates assembler logic: clip_start=10.0, segment at [10.0, 15.0] →
    adjusted to [0.0, 5.0]. ASS Dialogue lines must start at 0:00:00.00.
    """
    from sable.clip.captions import generate_word_captions

    clip_start = 10.0
    raw_segment = {"start": 10.0, "end": 15.0, "text": "hello world"}
    # Apply the same offset the assembler applies
    adjusted = {
        **raw_segment,
        "start": raw_segment["start"] - clip_start,
        "end":   raw_segment["end"] - clip_start,
    }

    out = tmp_path / "test.ass"
    generate_word_captions([adjusted], out, style="phrase")

    content = out.read_text()
    assert "0:00:00.00" in content
    assert "0:00:10.00" not in content
