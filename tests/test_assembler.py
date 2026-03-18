"""Tests for clip assembler dry-run mode."""
import pytest


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setenv("SABLE_WORKSPACE", str(tmp_path / "workspace"))


def test_assembler_dry_run(tmp_path):
    from sable.clip.assembler import assemble_clip

    meta = assemble_clip(
        source_video=str(tmp_path / "fake.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        start=0.0,
        end=30.0,
        account_handle="@test",
        dry_run=True,
    )
    assert meta["dry_run"] is True
    assert meta["duration"] == 30.0
    assert not (tmp_path / "out.mp4").exists()
