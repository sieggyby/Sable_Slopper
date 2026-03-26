"""Tests for clip selector dry-run logic."""
import json
import pytest


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))


def test_selector_dry_run():
    from sable.roster.models import Account
    from sable.clip.selector import select_clips

    acc = Account(handle="@test", persona_archetype="degen")
    transcript = {
        "text": "This is a test transcript about DeFi and crypto.",
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "This is a test"},
            {"start": 5.0, "end": 30.0, "text": "transcript about DeFi and crypto."},
        ],
    }

    clips = select_clips(transcript, acc, max_clips=2, dry_run=True)
    assert len(clips) == 1  # dry run returns 1 clip
    assert clips[0]["reason"].startswith("DRY RUN — first 30s")
    assert clips[0]["start"] == 0.0


def test_selector_respects_max_duration():
    from sable.roster.models import Account
    from sable.clip.selector import select_clips

    acc = Account(handle="@test")
    transcript = {"text": "test", "segments": []}

    clips = select_clips(transcript, acc, max_duration=20.0, dry_run=True)
    assert clips[0]["end"] <= 20.0


def _make_transcript_with_windows(n: int) -> dict:
    """Build a fake transcript that produces n speech windows via _find_windows."""
    # Use word-level timestamps with large gaps to force window splits
    words = []
    segments = []
    t = 0.0
    gap = 1.5  # > _PAUSE_THRESHOLD (0.8s) — each word becomes its own window
    for i in range(n):
        word_start = t
        word_end = t + 6.0  # 6s word duration > _MIN_WINDOW_DURATION (5.0s)
        words.append({"start": word_start, "end": word_end, "text": f"word{i}"})
        segments.append({
            "start": word_start,
            "end": word_end,
            "text": f"This is sentence {i}.",
        })
        t = word_end + gap
    return {"segments": segments, "words": words}


def test_select_clips_logs_batch_count_for_large_transcript(monkeypatch, caplog):
    """With >_MAX_WINDOW_CONTEXT windows, an INFO log should mention the batch count."""
    import logging
    from unittest.mock import patch
    from sable.roster.models import Account
    from sable.clip.selector import select_clips, _MAX_WINDOW_CONTEXT

    acc = Account(handle="@test", persona_archetype="degen")
    transcript = _make_transcript_with_windows(_MAX_WINDOW_CONTEXT + 5)

    with patch("sable.clip.selector.call_claude_json", return_value="[]"), \
         caplog.at_level(logging.INFO, logger="sable.clip.selector"):
        select_clips(transcript, acc)

    batch_logs = [r for r in caplog.records if "2 batches" in r.message]
    assert len(batch_logs) >= 1, "Expected INFO log about batch count"


def test_select_clips_calls_claude_once_per_batch(monkeypatch):
    """With 100 windows, call_claude_json is called exactly 2 times (2 first-stage batches)."""
    from unittest.mock import patch
    from sable.roster.models import Account
    from sable.clip.selector import select_clips

    acc = Account(handle="@test", persona_archetype="degen")
    transcript = _make_transcript_with_windows(100)

    call_count = [0]

    def fake_call_claude(prompt, max_tokens=None):
        call_count[0] += 1
        return "[]"

    with patch("sable.clip.selector.call_claude_json", side_effect=fake_call_claude):
        result = select_clips(transcript, acc)

    # 100 windows → 2 batches of 80/20; no clips → no eval batch call
    assert call_count[0] == 2, f"Expected 2 calls (2 batches), got {call_count[0]}"
    assert result == []


def test_select_clips_offsets_indices_from_second_batch(monkeypatch):
    """Second batch local index 0 maps to absolute index _MAX_WINDOW_CONTEXT."""
    from unittest.mock import patch
    from sable.roster.models import Account
    from sable.clip.selector import select_clips, _MAX_WINDOW_CONTEXT

    acc = Account(handle="@test", persona_archetype="degen")
    transcript = _make_transcript_with_windows(100)

    second_batch_result = json.dumps([{
        "windows": [0],
        "reason": "test clip",
        "hook": "hook text",
        "caption_hint": "caption",
        "score": 8,
        "format": "standard",
    }])
    call_results = ["[]", second_batch_result]
    call_idx = [0]

    def fake_call_claude(prompt, max_tokens=None):
        r = call_results[call_idx[0]]
        call_idx[0] += 1
        return r

    captured_selections = []

    def fake_resolve_clip(sel, windows, *args, **kwargs):
        captured_selections.append(sel.copy())
        return None  # skip actual resolution; clips_with_variants stays empty

    with patch("sable.clip.selector.call_claude_json", side_effect=fake_call_claude), \
         patch("sable.clip.selector._resolve_clip", side_effect=fake_resolve_clip):
        select_clips(transcript, acc)

    assert len(captured_selections) == 1, "Expected exactly one resolved selection"
    assert captured_selections[0]["windows"] == [_MAX_WINDOW_CONTEXT], (
        f"Expected absolute index {_MAX_WINDOW_CONTEXT}, got {captured_selections[0]['windows']}"
    )
