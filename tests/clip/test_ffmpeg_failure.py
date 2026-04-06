"""AQ-15: FFmpeg failure mid-pipeline raises RuntimeError."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from sable.shared.ffmpeg import run


def test_called_process_error_raises_runtime_error():
    """subprocess.CalledProcessError → RuntimeError with actionable message."""
    err = subprocess.CalledProcessError(1, "ffmpeg", stderr="Unknown encoder")
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(RuntimeError, match="FFmpeg failed"):
            run(["ffmpeg", "-i", "input.mp4", "output.mp4"])


def test_timeout_expired_raises_runtime_error():
    """subprocess.TimeoutExpired → RuntimeError with timeout message."""
    err = subprocess.TimeoutExpired("ffmpeg", 300)
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(RuntimeError, match="timed out after 300s"):
            run(["ffmpeg", "-i", "input.mp4", "output.mp4"])


def test_file_not_found_raises_runtime_error():
    """Missing ffmpeg binary → RuntimeError."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError, match="Command not found"):
            run(["ffmpeg", "-i", "input.mp4", "output.mp4"])
