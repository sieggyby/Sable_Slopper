"""Tests for sable.clip.review."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sable.clip.review import (
    ClipCandidate,
    approve_clip,
    find_unreviewed_clips,
    reject_clip,
)


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setenv("SABLE_WORKSPACE", str(tmp_path / "workspace"))


def _make_account(handle: str, org: str):
    acc = MagicMock()
    acc.handle = handle
    acc.org = org
    return acc


def _write_clip_meta(ws: Path, handle: str, name: str, meta: dict) -> Path:
    """Write a .meta.json sidecar in workspace/output/@handle/clips/."""
    clip_dir = ws / "output" / handle / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    meta_path = clip_dir / f"{name}.meta.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    # Create a dummy clip file
    clip_path = clip_dir / f"{name}.mp4"
    clip_path.write_bytes(b"fake video")
    return meta_path


class TestFindUnreviewedClips:
    def test_finds_clips_without_vault_note_id(self, tmp_path):
        ws = tmp_path / "workspace"
        _write_clip_meta(ws, "@alice", "clip_001", {
            "duration": 15.0, "caption": "hello world this is a test",
        })
        _write_clip_meta(ws, "@alice", "clip_002", {
            "duration": 20.0, "caption": "already reviewed",
            "vault_note_id": "clip-001",
        })

        with patch("sable.roster.manager.list_accounts") as mock_list, \
             patch("sable.shared.paths.workspace", return_value=ws):
            mock_list.return_value = [_make_account("@alice", "test_org")]
            candidates = find_unreviewed_clips("test_org")

        assert len(candidates) == 1
        assert candidates[0].meta_path.name == "clip_001.meta.json"
        assert candidates[0].duration == 15.0

    def test_empty_when_all_reviewed(self, tmp_path):
        ws = tmp_path / "workspace"
        _write_clip_meta(ws, "@alice", "clip_001", {
            "duration": 15.0, "vault_note_id": "clip-001",
        })

        with patch("sable.roster.manager.list_accounts") as mock_list, \
             patch("sable.shared.paths.workspace", return_value=ws):
            mock_list.return_value = [_make_account("@alice", "test_org")]
            candidates = find_unreviewed_clips("test_org")

        assert len(candidates) == 0

    def test_transcript_excerpt_truncated(self, tmp_path):
        ws = tmp_path / "workspace"
        long_caption = " ".join(f"word{i}" for i in range(100))
        _write_clip_meta(ws, "@alice", "clip_001", {
            "duration": 30.0, "caption": long_caption,
        })

        with patch("sable.roster.manager.list_accounts") as mock_list, \
             patch("sable.shared.paths.workspace", return_value=ws):
            mock_list.return_value = [_make_account("@alice", "test_org")]
            candidates = find_unreviewed_clips("test_org")

        assert len(candidates) == 1
        assert candidates[0].transcript_excerpt.endswith("...")
        assert len(candidates[0].transcript_excerpt.split()) <= 51  # 50 words + "..."

    def test_score_parsed(self, tmp_path):
        ws = tmp_path / "workspace"
        _write_clip_meta(ws, "@alice", "clip_001", {
            "duration": 15.0, "caption": "test", "score": 8,
        })

        with patch("sable.roster.manager.list_accounts") as mock_list, \
             patch("sable.shared.paths.workspace", return_value=ws):
            mock_list.return_value = [_make_account("@alice", "test_org")]
            candidates = find_unreviewed_clips("test_org")

        assert candidates[0].selection_score == 8.0


class TestApproveClip:
    def test_stamps_vault_note_id(self, tmp_path):
        meta = {"duration": 15.0, "caption": "test"}
        meta_path = tmp_path / "clip_001.meta.json"
        meta_path.write_text(json.dumps(meta))

        candidate = ClipCandidate(
            clip_path=tmp_path / "clip_001.mp4",
            meta_path=meta_path,
            meta=meta,
            duration=15.0,
            transcript_excerpt="test",
            selection_score=None,
        )

        approve_clip(candidate, "clip-review-001")

        updated = json.loads(meta_path.read_text())
        assert updated["vault_note_id"] == "clip-review-001"


class TestRejectClip:
    def test_moves_to_rejected(self, tmp_path):
        clip_dir = tmp_path / "clips"
        clip_dir.mkdir()
        meta_path = clip_dir / "clip_001.meta.json"
        clip_path = clip_dir / "clip_001.mp4"
        meta_path.write_text(json.dumps({"duration": 15.0}))
        clip_path.write_bytes(b"fake")

        candidate = ClipCandidate(
            clip_path=clip_path,
            meta_path=meta_path,
            meta={"duration": 15.0},
            duration=15.0,
            transcript_excerpt="",
            selection_score=None,
        )

        reject_clip(candidate)

        assert not meta_path.exists()
        assert not clip_path.exists()
        rejected = clip_dir / "_rejected"
        assert rejected.exists()
        assert (rejected / "clip_001.meta.json").exists()
        assert (rejected / "clip_001.mp4").exists()

    def test_handles_missing_clip(self, tmp_path):
        clip_dir = tmp_path / "clips"
        clip_dir.mkdir()
        meta_path = clip_dir / "clip_001.meta.json"
        meta_path.write_text(json.dumps({"duration": 15.0}))

        candidate = ClipCandidate(
            clip_path=clip_dir / "clip_001.mp4",  # doesn't exist
            meta_path=meta_path,
            meta={"duration": 15.0},
            duration=15.0,
            transcript_excerpt="",
            selection_score=None,
        )

        reject_clip(candidate)

        assert not meta_path.exists()
        assert (clip_dir / "_rejected" / "clip_001.meta.json").exists()
