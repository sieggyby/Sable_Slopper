"""Tests for sable.clip.brainrot module."""
import logging
import warnings

import pytest


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setenv("SABLE_WORKSPACE", str(tmp_path / "workspace"))


def test_loop_to_duration_caps_at_30(tmp_path, monkeypatch, caplog):
    """loop_to_duration caps at 30 loops and warns when src_duration is very short."""
    from sable.clip.brainrot import loop_to_duration

    # Create a fake video file
    fake_video = tmp_path / "brainrot.mp4"
    fake_video.write_bytes(b"fake video")

    output_path = tmp_path / "out.mp4"

    # Mock get_duration to return 0.1s (very short) and run to no-op
    import sable.clip.brainrot as brainrot_mod
    monkeypatch.setattr(brainrot_mod, "get_duration", lambda p: 0.1)

    ffmpeg_calls = []

    def fake_run(cmd, capture=False):
        ffmpeg_calls.append(cmd)

    monkeypatch.setattr(brainrot_mod, "run", fake_run)
    monkeypatch.setattr(brainrot_mod, "require_ffmpeg", lambda: "ffmpeg")

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        loop_to_duration(
            video_path=str(fake_video),
            target_duration=60.0,
            output_path=str(output_path),
        )

    # Should have been capped at 30
    assert len(ffmpeg_calls) == 1
    cmd = ffmpeg_calls[0]
    stream_loop_idx = cmd.index("-stream_loop")
    assert cmd[stream_loop_idx + 1] == "30", f"Expected loops=30, got {cmd[stream_loop_idx + 1]}"

    # Warning should have been emitted
    runtime_warnings = [w for w in caught_warnings if issubclass(w.category, RuntimeWarning)]
    assert len(runtime_warnings) >= 1, "Expected RuntimeWarning about capped loops"
    assert any(
        "30" in str(w.message) or "capped" in str(w.message).lower()
        for w in runtime_warnings
    ), f"Warning message should mention 30 or 'capped', got: {[str(w.message) for w in runtime_warnings]}"
