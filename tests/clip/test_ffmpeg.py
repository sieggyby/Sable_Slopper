"""Tests for sable.shared.ffmpeg — error parsing, bitrate doubling, subtitle path validation."""
import pytest


def test_parse_ffmpeg_error_extracts_last_non_progress_line():
    from sable.shared.ffmpeg import _parse_ffmpeg_error

    stderr = (
        "frame=100 fps=30 q=28.0 size=    512kB time=00:00:04.00\n"
        "size=1024kB time=00:00:08.00 bitrate= 128.0kbits/s\n"
        "frame=200 fps=30 q=28.0 size=   2048kB time=00:00:16.00\n"
        "Error opening output file output.mp4\n"
        "Error initializing output stream: No such file or directory\n"
    )
    result = _parse_ffmpeg_error(stderr)

    assert result == "Error initializing output stream: No such file or directory"


@pytest.mark.parametrize("rate,expected", [
    ("4M",  "8M"),
    ("128k", "256k"),
    ("512", "1024"),
])
def test_double_rate_handles_M_and_k_suffixes(rate, expected):
    from sable.shared.ffmpeg import _double_rate

    assert _double_rate(rate) == expected


@pytest.mark.parametrize("char", ["[", ";", ":", "="])
def test_validate_subtitle_path_raises_on_special_chars(tmp_path, char):
    from sable.shared.ffmpeg import _validate_subtitle_path
    from sable.platform.errors import SableError, INVALID_PATH

    bad_path = str(tmp_path / f"sub{char}title.ass")
    with pytest.raises(SableError) as exc_info:
        _validate_subtitle_path(bad_path)

    assert exc_info.value.code == INVALID_PATH
