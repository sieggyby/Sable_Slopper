"""Tests for sable.clip.assembler — platform profiles, audio_only color, clip-only brainrot skip."""
import pytest
from pathlib import Path
from unittest.mock import patch


def test_assemble_clip_platform_profiles_applied_correctly(tmp_path, monkeypatch):
    """platform='discord' → stack_videos receives profile with crf=28, video_maxrate='4M'."""
    source = tmp_path / "src.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out.mp4"
    brainrot = tmp_path / "brain.mp4"
    brainrot.write_bytes(b"x")

    profile_received = {}

    def fake_stack(top_path, bottom_path, output_path,
                   subtitle_path=None, image_overlay_path=None,
                   profile=None, **kw):
        profile_received.update(profile or {})
        Path(output_path).write_bytes(b"x")

    with patch("sable.clip.assembler.extract_clip"), \
         patch("sable.clip.assembler.pick_brainrot", return_value=str(brainrot)), \
         patch("sable.clip.assembler.loop_to_duration"), \
         patch("sable.clip.assembler.stack_videos", side_effect=fake_stack), \
         patch("sable.clip.assembler.generate_thumbnail"):

        from sable.clip.assembler import assemble_clip
        assemble_clip(
            source_video=str(source),
            output_path=str(output),
            start=0.0, end=30.0,
            account_handle="@test",
            platform="discord",
            brainrot_energy="medium",
            caption_style="none",
            caption_color="yellow",  # skip _auto_caption_color
        )

    assert profile_received["crf"] == 28
    assert profile_received["video_maxrate"] == "4M"


def test_assemble_clip_audio_only_sets_yellow_caption_color(tmp_path, monkeypatch):
    """audio_only=True, caption_color=None → resolved_color='yellow' without sampling."""
    import sable.clip.assembler as asm
    monkeypatch.setattr(
        asm,
        "_auto_caption_color",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("_auto_caption_color must not be called")),
    )

    from sable.clip.assembler import assemble_clip
    meta = assemble_clip(
        source_video=str(tmp_path / "src.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        start=0.0, end=30.0,
        account_handle="@test",
        audio_only=True,
        caption_color=None,
        dry_run=True,
    )

    assert meta["caption_color"] == "yellow"


def test_assemble_clip_clip_only_skips_brainrot(tmp_path, monkeypatch):
    """brainrot_energy='none' → pick_brainrot never called; no brainrot_source in meta."""
    import sable.clip.assembler as asm
    monkeypatch.setattr(
        asm,
        "pick_brainrot",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("pick_brainrot must not be called")),
    )

    from sable.clip.assembler import assemble_clip
    meta = assemble_clip(
        source_video=str(tmp_path / "src.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        start=0.0, end=30.0,
        account_handle="@test",
        brainrot_energy="none",
        caption_color="yellow",
        dry_run=True,
    )

    assert "brainrot_source" not in meta
