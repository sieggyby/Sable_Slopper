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

    p1 = _cache_path(f, "base.en")
    p2 = _cache_path(f, "base.en")
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


def test_model_cache_reuses_instance(monkeypatch):
    """_get_model returns the same instance on repeated calls with the same args."""
    import sable.clip.transcribe as transcribe_mod
    monkeypatch.setattr(transcribe_mod, "_MODEL_CACHE", {})

    call_count = {"n": 0}

    class FakeModel:
        pass

    def fake_init(model, device, compute_type):
        call_count["n"] += 1
        return FakeModel()

    def patched_get_model(model):
        if model not in transcribe_mod._MODEL_CACHE:
            transcribe_mod._MODEL_CACHE[model] = fake_init(model, "auto", "int8")
        return transcribe_mod._MODEL_CACHE[model]

    monkeypatch.setattr(transcribe_mod, "_get_model", patched_get_model)

    m1 = transcribe_mod._get_model("base.en")
    m2 = transcribe_mod._get_model("base.en")
    assert m1 is m2, "Same model instance should be returned from cache"
    assert call_count["n"] == 1, f"WhisperModel constructor should be called once, got {call_count['n']}"
    transcribe_mod._MODEL_CACHE.clear()


def test_normalize_faster_whisper():
    from types import SimpleNamespace
    from sable.clip.transcribe import _normalize_faster_whisper

    w1 = SimpleNamespace(word="Hello", start=0.0, end=0.5)
    w2 = SimpleNamespace(word=" world", start=0.5, end=1.0)
    seg = SimpleNamespace(text="Hello world", start=0.0, end=1.0, words=[w1, w2])
    result = _normalize_faster_whisper([seg])
    assert "text" in result
    assert "segments" in result
    assert "words" in result
    assert result["segments"][0]["start"] == 0.0
    assert result["segments"][0]["end"] == 1.0
    assert result["words"][0]["start"] == 0.0
    assert result["words"][0]["end"] == 0.5
