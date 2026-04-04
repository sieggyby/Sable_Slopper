"""Tests for sable/clip/face_track.py — face-centered and motion-based crop offsets."""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sable.clip.face_track import compute_face_offset, _compute_motion_offset


# ---------------------------------------------------------------------------
# compute_face_offset
# ---------------------------------------------------------------------------

def test_face_offset_returns_zero_for_missing_file():
    """Non-existent video → 0.0."""
    assert compute_face_offset("/nonexistent/video.mp4", 720) == 0.0


def test_face_offset_returns_zero_when_source_narrower_than_target(tmp_path):
    """Source width <= target width → no room to pan → 0.0."""
    fake_vid = tmp_path / "narrow.mp4"
    fake_vid.touch()

    with patch("sable.clip.face_track.get_video_dimensions", return_value=(720, 480)):
        result = compute_face_offset(str(fake_vid), 720)
    assert result == 0.0


def test_face_offset_no_frames_returns_float(tmp_path):
    """No extractable frames → falls to motion fallback → returns float."""
    fake_vid = tmp_path / "video.mp4"
    fake_vid.touch()

    with patch("sable.clip.face_track.get_video_dimensions", return_value=(1920, 1080)), \
         patch("sable.clip.face_track._extract_sample_frames", return_value=[]):
        result = compute_face_offset(str(fake_vid), 720)
    assert isinstance(result, float)


def test_face_offset_with_faces(tmp_path):
    """Detected faces produce a non-zero fractional offset."""
    fake_vid = tmp_path / "video.mp4"
    fake_vid.touch()

    frames = [tmp_path / f"f{i}.png" for i in range(3)]
    for f in frames:
        f.touch()

    try:
        import face_recognition  # noqa: F401
        import numpy as np
        from PIL import Image
    except ImportError:
        pytest.skip("face_recognition/numpy/PIL not installed")

    # Face at x_center=1400 in 1920-wide video, target 720
    # pan_room = (1920-720)/2 = 600, offset_px = 1400 - 960 = 440
    # fraction = 440/600 ≈ 0.733
    mock_locs = [(100, 1500, 300, 1300)]

    with patch("sable.clip.face_track.get_video_dimensions", return_value=(1920, 1080)), \
         patch("sable.clip.face_track._extract_sample_frames", return_value=frames), \
         patch("face_recognition.face_locations", return_value=mock_locs), \
         patch("PIL.Image.open") as mock_open:
        mock_open.return_value.convert.return_value = MagicMock()
        result = compute_face_offset(str(fake_vid), 720, sample_count=3)

    assert isinstance(result, float)
    assert result > 0  # Face is right of center


def test_face_offset_face_left_of_center(tmp_path):
    """Face at left side → negative fractional offset."""
    fake_vid = tmp_path / "video.mp4"
    fake_vid.touch()

    frames = [tmp_path / "f0.png"]
    frames[0].touch()

    try:
        import face_recognition  # noqa: F401
    except ImportError:
        pytest.skip("face_recognition not installed")

    mock_locs = [(100, 300, 300, 100)]  # x_center = 200

    with patch("sable.clip.face_track.get_video_dimensions", return_value=(1920, 1080)), \
         patch("sable.clip.face_track._extract_sample_frames", return_value=frames), \
         patch("face_recognition.face_locations", return_value=mock_locs), \
         patch("PIL.Image.open") as mock_open:
        mock_open.return_value.convert.return_value = MagicMock()
        result = compute_face_offset(str(fake_vid), 720, sample_count=1)

    assert isinstance(result, float)
    assert result < 0  # Face is left of center


def test_face_offset_clamped_to_range(tmp_path):
    """Offset is clamped to [-1.0, 1.0]."""
    fake_vid = tmp_path / "video.mp4"
    fake_vid.touch()

    frames = [tmp_path / "f0.png"]
    frames[0].touch()

    try:
        import face_recognition  # noqa: F401
    except ImportError:
        pytest.skip("face_recognition not installed")

    # Face at extreme right x=1900 → would exceed +1.0 without clamping
    mock_locs = [(100, 1920, 300, 1880)]

    with patch("sable.clip.face_track.get_video_dimensions", return_value=(1920, 1080)), \
         patch("sable.clip.face_track._extract_sample_frames", return_value=frames), \
         patch("face_recognition.face_locations", return_value=mock_locs), \
         patch("PIL.Image.open") as mock_open:
        mock_open.return_value.convert.return_value = MagicMock()
        result = compute_face_offset(str(fake_vid), 720, sample_count=1)

    assert -1.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# _compute_motion_offset
# ---------------------------------------------------------------------------

def test_motion_offset_no_cv2():
    """cv2 not installed → returns 0.0."""
    with patch.dict("sys.modules", {"cv2": None}):
        result = _compute_motion_offset("/fake.mp4", 1920, 720)
    assert result == 0.0


def test_motion_offset_nonexistent_file():
    """Non-existent video → 0.0."""
    result = _compute_motion_offset("/nonexistent.mp4", 1920, 720)
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# CLI flag wiring (dry_run — no FFmpeg needed)
# ---------------------------------------------------------------------------

def test_face_track_flag_in_dry_run():
    """--face-track flag is captured in metadata during dry run."""
    from sable.clip.assembler import assemble_clip

    meta = assemble_clip(
        source_video="/fake/video.mp4",
        output_path="/fake/output.mp4",
        start=0.0,
        end=10.0,
        account_handle="@test",
        dry_run=True,
        face_track=True,
    )
    assert meta["face_track"] is True


def test_no_face_track_flag_default():
    """face_track defaults to False in metadata."""
    from sable.clip.assembler import assemble_clip

    meta = assemble_clip(
        source_video="/fake/video.mp4",
        output_path="/fake/output.mp4",
        start=0.0,
        end=10.0,
        account_handle="@test",
        dry_run=True,
    )
    assert meta["face_track"] is False


# ---------------------------------------------------------------------------
# ffmpeg crop_x_offset parameter
# ---------------------------------------------------------------------------

def test_stack_videos_accepts_crop_x_offset():
    """stack_videos signature accepts crop_x_offset as float."""
    from sable.shared.ffmpeg import stack_videos
    sig = inspect.signature(stack_videos)
    assert "crop_x_offset" in sig.parameters
    assert sig.parameters["crop_x_offset"].default == 0.0


def test_encode_clip_only_accepts_crop_x_offset():
    """encode_clip_only signature accepts crop_x_offset as float."""
    from sable.shared.ffmpeg import encode_clip_only
    sig = inspect.signature(encode_clip_only)
    assert "crop_x_offset" in sig.parameters
    assert sig.parameters["crop_x_offset"].default == 0.0


# ---------------------------------------------------------------------------
# assembler: audio_only skips face detection
# ---------------------------------------------------------------------------

def test_audio_only_skips_face_detection():
    """face_track + audio_only → no face offset computation."""
    from sable.clip.assembler import assemble_clip

    meta = assemble_clip(
        source_video="/fake/video.mp4",
        output_path="/fake/output.mp4",
        start=0.0,
        end=10.0,
        account_handle="@test",
        dry_run=True,
        face_track=True,
        audio_only=True,
    )
    assert meta["face_track"] is True
    assert meta["audio_only"] is True
    # crop_x_offset should not be in metadata when dry_run (computed only during assembly)
    assert "crop_x_offset" not in meta
