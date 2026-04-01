"""Tests for sable.clip.transcribe — word timing fixes and transcript caching."""
import json
import pytest


def test_fix_word_timing_removes_overlap_by_midpoint():
    from sable.clip.transcribe import _fix_word_timing

    # cur["end"]=1.0, nxt["start"]=0.8 → mid=0.9; both adjusted to 0.9
    words = [
        {"start": 0.0, "end": 1.0, "text": "hello"},
        {"start": 0.8, "end": 1.5, "text": "world"},
    ]
    result = _fix_word_timing(words)

    assert result[0]["end"] == pytest.approx(0.9)
    assert result[1]["start"] == pytest.approx(0.9)


def test_fix_word_timing_fills_micro_gaps():
    from sable.clip.transcribe import _fix_word_timing

    # 60ms gap < 80ms threshold → fill (extend word1 end to nxt["start"])
    # 90ms gap ≥ 80ms threshold → NOT filled
    words_fill = [
        {"start": 0.0, "end": 1.0, "text": "w1"},
        {"start": 1.06, "end": 2.0, "text": "w2"},  # gap=0.06 < 0.08
    ]
    result_fill = _fix_word_timing(words_fill)
    assert result_fill[0]["end"] == pytest.approx(1.06)

    words_no_fill = [
        {"start": 0.0, "end": 1.0, "text": "w1"},
        {"start": 1.09, "end": 2.0, "text": "w2"},  # gap=0.09 ≥ 0.08
    ]
    result_no_fill = _fix_word_timing(words_no_fill)
    assert result_no_fill[0]["end"] == pytest.approx(1.0)  # unchanged


def test_fix_word_timing_enforces_minimum_100ms_duration():
    from sable.clip.transcribe import _fix_word_timing

    # 50ms word → extended to 100ms; next word at 1.0 → no overlap introduced
    words = [
        {"start": 0.0, "end": 0.05, "text": "tiny"},
        {"start": 1.0, "end": 2.0, "text": "next"},
    ]
    result = _fix_word_timing(words)

    assert result[0]["end"] == pytest.approx(0.1)
    assert result[1]["start"] == pytest.approx(1.0)  # unchanged


def test_transcribe_uses_cache_on_second_call(tmp_path, monkeypatch):
    """Cache hit: returns stored JSON without calling _get_model."""
    import sable.clip.transcribe as t_mod

    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"fake video data")

    cache_data = {"text": "hello world", "segments": [], "words": []}

    from sable.clip.transcribe import _cache_path
    cp = _cache_path(fake_video, "base.en")
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(cache_data))

    monkeypatch.setattr(
        t_mod,
        "_get_model",
        lambda m: (_ for _ in ()).throw(AssertionError("_get_model must not be called on cache hit")),
    )

    from sable.clip.transcribe import transcribe
    result = transcribe(str(fake_video), model="base.en")

    assert result == cache_data


def test_transcribe_passes_condition_on_previous_text_false(tmp_path, monkeypatch):
    """Whisper transcribe call must include condition_on_previous_text=False."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    import sable.clip.transcribe as t_mod

    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"fake video data")

    captured_kwargs = {}
    w1 = SimpleNamespace(word="hello", start=0.0, end=0.5)
    seg = SimpleNamespace(text="hello", start=0.0, end=0.5, words=[w1])

    mock_model = MagicMock()

    def fake_transcribe(path, **kwargs):
        captured_kwargs.update(kwargs)
        return iter([seg]), SimpleNamespace(language="en")

    mock_model.transcribe = fake_transcribe
    monkeypatch.setattr(t_mod, "_get_model", lambda m: mock_model)

    t_mod.transcribe(str(fake_video), model="base.en", force=True)

    assert "condition_on_previous_text" in captured_kwargs, \
        "condition_on_previous_text must be passed to wm.transcribe()"
    assert captured_kwargs["condition_on_previous_text"] is False, \
        "condition_on_previous_text must be False to prevent hallucination cascades"
