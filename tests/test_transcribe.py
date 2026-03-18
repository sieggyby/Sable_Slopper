"""Tests for transcript caching logic (without actual whisper)."""
import pytest
import json
from pathlib import Path


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setenv("SABLE_WORKSPACE", str(tmp_path / "workspace"))


def test_cache_path_deterministic(tmp_path):
    from sable.clip.transcribe import _cache_path, _file_hash

    # Create a test file
    f = tmp_path / "test.mp4"
    f.write_bytes(b"fake video data")

    p1 = _cache_path(f)
    p2 = _cache_path(f)
    assert p1 == p2
    assert p1.suffix == ".json"


def test_file_hash_consistent(tmp_path):
    from sable.clip.transcribe import _file_hash

    f = tmp_path / "file.mp4"
    f.write_bytes(b"some content")
    h1 = _file_hash(f)
    h2 = _file_hash(f)
    assert h1 == h2
    assert len(h1) == 16


def test_normalize_whisper_output():
    from sable.clip.transcribe import _normalize_whisper_output

    raw = {
        "transcription": [
            {
                "text": "Hello world",
                "offsets": {"from": 0, "to": 1000},
                "tokens": [
                    {"text": "Hello", "offsets": {"from": 0, "to": 500}},
                    {"text": " world", "offsets": {"from": 500, "to": 1000}},
                ],
            }
        ]
    }
    result = _normalize_whisper_output(raw)
    assert "text" in result
    assert "segments" in result
    assert len(result["segments"]) == 2
    assert result["segments"][0]["start"] == 0.0
    assert result["segments"][0]["end"] == 0.5
