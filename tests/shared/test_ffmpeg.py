"""Tests for sable.shared.ffmpeg — T3-2: command construction and error handling."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from sable.shared.ffmpeg import run, extract_clip, extract_audio


# ---------------------------------------------------------------------------
# run() error handling
# ---------------------------------------------------------------------------

def test_run_raises_on_subprocess_error():
    """CalledProcessError → RuntimeError with message."""
    with patch("sable.shared.ffmpeg.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["ffmpeg"], stderr="Invalid data found"
        )
        with pytest.raises(RuntimeError, match="FFmpeg failed"):
            run(["ffmpeg", "-i", "in.mp4", "out.mp4"])


def test_run_raises_on_timeout():
    """TimeoutExpired → RuntimeError with timeout message."""
    with patch("sable.shared.ffmpeg.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["ffmpeg"], timeout=300
        )
        with pytest.raises(RuntimeError, match="timed out"):
            run(["ffmpeg", "-i", "in.mp4", "out.mp4"])


def test_run_raises_on_missing_binary():
    """FileNotFoundError → RuntimeError with install hint."""
    with patch("sable.shared.ffmpeg.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(RuntimeError, match="not found"):
            run(["ffmpeg", "-i", "in.mp4", "out.mp4"])


def test_run_success():
    """Successful run returns CompletedProcess."""
    with patch("sable.shared.ffmpeg.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(["ffmpeg"], 0)
        result = run(["ffmpeg", "-version"], check=False)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# extract_clip command construction
# ---------------------------------------------------------------------------

def test_extract_clip_command():
    """extract_clip passes -ss, -t, and -c copy."""
    with patch("sable.shared.ffmpeg.run") as mock_run, \
         patch("sable.shared.ffmpeg.require_ffmpeg", return_value="ffmpeg"):
        extract_clip("in.mp4", "out.mp4", start=10.5, end=25.0)

    args = mock_run.call_args[0][0]
    assert "-ss" in args
    ss_idx = args.index("-ss")
    assert args[ss_idx + 1] == "10.5"
    assert "-t" in args
    t_idx = args.index("-t")
    assert args[t_idx + 1] == "14.5"


# ---------------------------------------------------------------------------
# extract_audio command construction
# ---------------------------------------------------------------------------

def test_extract_audio_command():
    """extract_audio passes -vn and audio codec flags."""
    with patch("sable.shared.ffmpeg.run") as mock_run, \
         patch("sable.shared.ffmpeg.require_ffmpeg", return_value="ffmpeg"):
        extract_audio("in.mp4", "out.wav")

    args = mock_run.call_args[0][0]
    assert "-vn" in args
    assert "pcm_s16le" in args
