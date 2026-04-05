"""Tests for video face swap frame cap and cost logging."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


def test_swap_video_caps_frame_count(tmp_path):
    """Frame-by-frame swap caps at _MAX_FRAMES to prevent unbounded Replicate spend."""
    from sable.face.video import _MAX_FRAMES

    fake_frames = [tmp_path / f"frame_{i:06d}.png" for i in range(800)]
    for f in fake_frames:
        f.write_bytes(b"\x89PNG")

    swap_calls = []

    def fake_swap(source, ref, dest, **kwargs):
        swap_calls.append(source)
        Path(dest).write_bytes(b"\x89PNG")
        return str(dest), "test_model"

    with patch("sable.face.video.extract_frames", return_value=fake_frames), \
         patch("sable.face.video.filter_frames_with_faces", side_effect=lambda x: x), \
         patch("sable.face.video.dedup_frames", side_effect=lambda x: x), \
         patch("sable.face.video.swap_image", side_effect=fake_swap), \
         patch("sable.face.video.reassemble_video"), \
         patch("sable.face.video.log_swap"), \
         patch("sable.face.video.get_duration", return_value=30.0):

        from sable.face.video import swap_video
        swap_video(
            tmp_path / "input.mp4", tmp_path / "ref.png", tmp_path / "out.mp4",
            quality="high",
        )

    assert len(swap_calls) == _MAX_FRAMES


def test_swap_video_no_cap_when_under_limit(tmp_path):
    """When frame count is under the cap, all frames are processed."""
    fake_frames = [tmp_path / f"frame_{i:06d}.png" for i in range(10)]
    for f in fake_frames:
        f.write_bytes(b"\x89PNG")

    swap_calls = []

    def fake_swap(source, ref, dest, **kwargs):
        swap_calls.append(source)
        Path(dest).write_bytes(b"\x89PNG")
        return str(dest), "test_model"

    with patch("sable.face.video.extract_frames", return_value=fake_frames), \
         patch("sable.face.video.filter_frames_with_faces", side_effect=lambda x: x), \
         patch("sable.face.video.dedup_frames", side_effect=lambda x: x), \
         patch("sable.face.video.swap_image", side_effect=fake_swap), \
         patch("sable.face.video.reassemble_video"), \
         patch("sable.face.video.log_swap"), \
         patch("sable.face.video.get_duration", return_value=30.0):

        from sable.face.video import swap_video
        swap_video(
            tmp_path / "input.mp4", tmp_path / "ref.png", tmp_path / "out.mp4",
            quality="high",
        )

    assert len(swap_calls) == 10
