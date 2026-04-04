"""Tests for sable.clip.selector — window detection, endpoint candidates, trim/backtrack, dedup, eval."""
import json
import pytest

from tests.clip.conftest import make_words, make_segments


# ---------------------------------------------------------------------------
# _find_windows
# ---------------------------------------------------------------------------

def test_find_windows_splits_on_pause_threshold():
    from sable.clip.selector import _find_windows

    # gap=0.7 < 0.8 (PAUSE_THRESHOLD) → same window
    # gap=1.0 ≥ 0.8 → new window
    words = [
        {"start": 0.0, "end": 4.0, "text": "w0"},
        {"start": 4.7, "end": 8.7, "text": "w1"},   # gap=0.7, same window
        {"start": 9.7, "end": 15.7, "text": "w2"},  # gap=1.0, new window
    ]
    segments = [
        {"start": 0.0, "end": 8.7, "text": "block one."},
        {"start": 9.7, "end": 15.7, "text": "block two."},
    ]
    windows = _find_windows(words, segments)

    # 0.7s gap does not split: w0+w1 are in the same window
    assert len(windows) == 2
    # first window starts at 0.0, covering w0 and w1
    assert windows[0]["start"] == 0.0
    assert windows[0]["end"] == 8.7
    # second window starts at 9.7 (split by 1.0s gap)
    assert windows[1]["start"] == 9.7


def test_find_windows_discards_short_windows():
    from sable.clip.selector import _find_windows

    words = [
        {"start": 0.0, "end": 4.99, "text": "short"},   # dur=4.99 < 5.0 → dropped
        {"start": 10.0, "end": 15.0, "text": "exact"},  # dur=5.0 ≥ 5.0 → kept
    ]
    segments = [
        {"start": 0.0, "end": 4.99, "text": "short window."},
        {"start": 10.0, "end": 15.0, "text": "kept window."},
    ]
    windows = _find_windows(words, segments)

    assert len(windows) == 1
    assert windows[0]["start"] == 10.0
    assert windows[0]["end"] == 15.0


def test_find_windows_fallback_uses_segments_when_no_words():
    from sable.clip.selector import _find_windows

    segments = [
        {"start": 0.0, "end": 4.9, "text": "too short"},
        {"start": 5.0, "end": 10.1, "text": "long enough"},
    ]
    windows = _find_windows([], segments)

    assert len(windows) == 1
    assert windows[0]["text"] == "long enough"


def test_find_windows_fallback_text_from_word_tokens_when_no_segment_overlap():
    from sable.clip.selector import _find_windows

    # Words form one window [0, 6]; segment center is 6.5 (outside [0, 6))
    words = [
        {"start": 0.0, "end": 1.0, "text": "hello"},
        {"start": 1.5, "end": 3.0, "text": "world"},
        {"start": 3.5, "end": 6.0, "text": "defi"},
    ]
    segments = [
        {"start": 6.0, "end": 7.0, "text": "center outside"},  # center=6.5 ≥ 6 → no overlap
    ]
    windows = _find_windows(words, segments)

    assert len(windows) == 1
    # text rebuilt from word tokens, not from the segment
    assert "hello" in windows[0]["text"]
    assert "defi" in windows[0]["text"]
    assert "center outside" not in windows[0]["text"]


# ---------------------------------------------------------------------------
# _candidate_endpoints
# ---------------------------------------------------------------------------

def test_candidate_endpoints_respects_min_dur_bound():
    from sable.clip.selector import _candidate_endpoints

    # Segment ending at 7.9; with min_dur=8.0, lo=8.0 → 7.9 < lo → excluded
    start = 0.0
    words = [
        {"start": 0.0, "end": 7.9, "text": "w1"},
        {"start": 10.3, "end": 15.0, "text": "w2"},
    ]
    segments = [
        {"start": 6.0, "end": 7.9, "text": "too early."},
        {"start": 8.5, "end": 10.0, "text": "in range."},
    ]
    candidates = _candidate_endpoints(start, words, segments, min_dur=8.0, max_dur=90.0)

    assert 7.9 not in candidates
    assert 10.0 in candidates


def test_candidate_endpoints_filters_by_pause_threshold():
    from sable.clip.selector import _candidate_endpoints

    # Need ≥ 3 primary candidates so the fallback (0.05s bar) does NOT trigger.
    # pause=0.10 < 0.15 → rejected from primary; pause ≥ 0.20 → accepted.
    start = 0.0
    words = [
        {"start": 0.0,  "end": 9.0,  "text": "w1"},
        {"start": 9.10, "end": 9.8,  "text": "w2"},  # pause after 9.0 = 0.10 → reject
        {"start": 10.0, "end": 11.0, "text": "w3"},
        {"start": 11.20,"end": 12.0, "text": "w4"},  # pause after 11.0 = 0.20 → accept
        {"start": 12.0, "end": 13.0, "text": "w5"},
        {"start": 13.20,"end": 14.0, "text": "w6"},  # pause after 13.0 = 0.20 → accept
        {"start": 14.0, "end": 15.0, "text": "w7"},
        {"start": 15.40,"end": 20.0, "text": "w8"},  # pause after 15.0 = 0.40 → accept
    ]
    segments = [
        {"start": 8.0,  "end": 9.0,  "text": "short pause."},   # pause=0.10
        {"start": 10.0, "end": 11.0, "text": "primary one."},
        {"start": 12.0, "end": 13.0, "text": "primary two."},
        {"start": 14.0, "end": 15.0, "text": "primary three."},
    ]
    # 3 primary candidates → no fallback
    candidates = _candidate_endpoints(start, words, segments, min_dur=8.0, max_dur=90.0)

    assert 9.0 not in candidates   # pause=0.10 < 0.15 → rejected
    assert 11.0 in candidates      # pause=0.20 ≥ 0.15 → accepted
    assert 15.0 in candidates      # pause=0.40 ≥ 0.15 → accepted


def test_candidate_endpoints_fallback_lowers_bar_when_fewer_than_3():
    from sable.clip.selector import _candidate_endpoints

    # 2 primary candidates (pause ≥ 0.15); 2 extras (pause 0.10 ≥ 0.05)
    # Total after fallback: 4
    start = 0.0
    words = [
        {"start": 0.0, "end": 9.0, "text": "w1"},
        {"start": 9.20, "end": 10.0, "text": "w2"},  # pause after 9.0 = 0.20
        {"start": 10.0, "end": 11.0, "text": "w3"},
        {"start": 11.20, "end": 12.0, "text": "w4"}, # pause after 11.0 = 0.20
        {"start": 12.0, "end": 13.0, "text": "w5"},
        {"start": 13.10, "end": 14.0, "text": "w6"}, # pause after 13.0 = 0.10
        {"start": 14.0, "end": 15.0, "text": "w7"},
        {"start": 15.10, "end": 20.0, "text": "w8"}, # pause after 15.0 = 0.10
    ]
    segments = [
        {"start": 8.0,  "end": 9.0,  "text": "primary one."},
        {"start": 10.0, "end": 11.0, "text": "primary two."},
        {"start": 12.0, "end": 13.0, "text": "fallback one."},
        {"start": 14.0, "end": 15.0, "text": "fallback two."},
    ]
    candidates = _candidate_endpoints(start, words, segments, min_dur=8.0, max_dur=90.0)

    assert len(candidates) == 4
    assert 9.0 in candidates
    assert 11.0 in candidates
    assert 13.0 in candidates
    assert 15.0 in candidates


# ---------------------------------------------------------------------------
# _trim_leading_filler
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filler", ["so", "um", "yeah"])
def test_trim_leading_filler_removes_single_filler_token(filler):
    from sable.clip.selector import _trim_leading_filler

    words = [
        {"start": 0.0, "end": 0.5, "text": filler},
        {"start": 1.0, "end": 2.0, "text": "DeFi"},
    ]
    result = _trim_leading_filler(0.0, words)
    assert result == 1.0


def test_trim_leading_filler_removes_bigram_you_know():
    from sable.clip.selector import _trim_leading_filler

    words = [
        {"start": 0.0, "end": 0.5, "text": "you"},
        {"start": 0.6, "end": 1.0, "text": "know"},
        {"start": 1.5, "end": 2.5, "text": "DeFi"},
    ]
    result = _trim_leading_filler(0.0, words)
    assert result == 1.5


def test_trim_leading_filler_returns_none_when_all_filler():
    from sable.clip.selector import _trim_leading_filler

    words = [
        {"start": 0.0, "end": 0.5, "text": "so"},
        {"start": 1.0, "end": 1.5, "text": "um"},
        {"start": 2.0, "end": 2.5, "text": "yeah"},
    ]
    result = _trim_leading_filler(0.0, words)
    assert result is None


def test_trim_leading_filler_returns_none_when_move_negligible():
    from sable.clip.selector import _trim_leading_filler

    # First non-filler at start+0.09 < 0.1 threshold → negligible move
    words = [
        {"start": 0.0, "end": 0.05, "text": "so"},
        {"start": 0.09, "end": 0.5, "text": "DeFi"},
    ]
    result = _trim_leading_filler(0.0, words)
    assert result is None


# ---------------------------------------------------------------------------
# _backtrack_for_context
# ---------------------------------------------------------------------------

def test_backtrack_for_context_triggers_on_dangling_pattern():
    from sable.clip.selector import _backtrack_for_context

    words = [
        {"start": 3.5, "end": 4.5, "text": "prior"},
        {"start": 5.0, "end": 5.5, "text": "that's"},
        {"start": 5.6, "end": 5.9, "text": "why"},
        {"start": 6.0, "end": 7.0, "text": "DeFi"},
    ]
    segments = [
        {"start": 3.0, "end": 4.8, "text": "prior sentence."},
        {"start": 5.0, "end": 7.0, "text": "that's why DeFi matters."},
    ]
    result = _backtrack_for_context(
        start=5.0, words=words, segments=segments, max_dur=90.0, end=10.0
    )
    assert result == 3.0


def test_backtrack_aborts_when_crossing_window_boundary():
    from sable.clip.selector import _backtrack_for_context

    # Gap of 1.0s in [new_start, start] range → abort → None
    words = [
        {"start": 3.0, "end": 3.5, "text": "before"},
        {"start": 4.5, "end": 5.0, "text": "gap"},   # gap=4.5-3.5=1.0 ≥ 0.8
        {"start": 5.0, "end": 5.5, "text": "that's"},
        {"start": 5.6, "end": 5.9, "text": "why"},
        {"start": 6.0, "end": 7.0, "text": "it"},
    ]
    segments = [
        {"start": 3.0, "end": 4.8, "text": "prior."},
        {"start": 5.0, "end": 7.0, "text": "that's why it matters."},
    ]
    result = _backtrack_for_context(
        start=5.0, words=words, segments=segments, max_dur=90.0, end=10.0
    )
    assert result is None


def test_backtrack_aborts_when_exceeds_max_dur():
    from sable.clip.selector import _backtrack_for_context

    # end - new_start = 12.0 - 3.0 = 9.0 > max_dur=8.0 → None
    words = [
        {"start": 3.0, "end": 4.5, "text": "prior"},
        {"start": 5.0, "end": 5.5, "text": "that's"},
        {"start": 5.6, "end": 5.9, "text": "why"},
    ]
    segments = [
        {"start": 3.0, "end": 4.8, "text": "ok."},
        {"start": 5.0, "end": 6.0, "text": "that's why."},
    ]
    result = _backtrack_for_context(
        start=5.0, words=words, segments=segments, max_dur=8.0, end=12.0
    )
    assert result is None


def test_backtrack_aborts_when_backtrack_exceeds_12s():
    from sable.clip.selector import _backtrack_for_context

    # Prior segment 14s before clip start (> max_backtrack=12) → None
    words = [
        {"start": 1.5, "end": 2.5, "text": "prior"},
        {"start": 15.0, "end": 15.5, "text": "that's"},
        {"start": 15.6, "end": 15.9, "text": "why"},
    ]
    segments = [
        {"start": 1.0, "end": 2.8, "text": "far away."},
        {"start": 15.0, "end": 16.0, "text": "that's why."},
    ]
    result = _backtrack_for_context(
        start=15.0, words=words, segments=segments, max_dur=90.0, end=20.0
    )
    assert result is None


# ---------------------------------------------------------------------------
# _dedup_selections
# ---------------------------------------------------------------------------

def test_dedup_selections_higher_score_wins_on_overlap():
    from sable.clip.selector import _dedup_selections

    # Score=9 claims window 1; score=7 tries to claim window 1 → dropped
    sels = [
        {"windows": [1, 2], "score": 9, "reason": "high"},
        {"windows": [0, 1], "score": 7, "reason": "low"},
    ]
    result = _dedup_selections(sels)  # pre-sorted: 9 first
    assert len(result) == 1
    assert result[0]["score"] == 9


def test_dedup_selections_empty_windows_field_always_skipped():
    from sable.clip.selector import _dedup_selections

    sels = [
        {"windows": [], "score": 8, "reason": "empty"},
        {"windows": [1], "score": 5, "reason": "valid"},
    ]
    result = _dedup_selections(sels)
    assert len(result) == 1
    assert result[0]["score"] == 5


def test_dedup_selections_non_overlapping_both_survive():
    from sable.clip.selector import _dedup_selections

    sels = [
        {"windows": [0, 1], "score": 8},
        {"windows": [2, 3], "score": 6},
    ]
    result = _dedup_selections(sels)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# _evaluate_variants_batch
# ---------------------------------------------------------------------------

def _make_clip(start=0.0, short_end=10.0, medium_end=15.0, long_end=20.0):
    return {
        "start": start,
        "variants": {
            "short":  {"start": start, "end": short_end},
            "medium": {"start": start, "end": medium_end},
            "long":   {"start": start, "end": long_end},
        },
        "reason": "test reason",
        "hook": "hook text",
        "caption_hint": "caption",
        "score": 7,
    }


def test_evaluate_variants_batch_splits_when_over_20_clips(monkeypatch):
    from sable.clip.selector import _evaluate_variants_batch

    call_count = [0]

    def fake_claude(prompt, max_tokens=None, **kwargs):
        call_count[0] += 1
        return "[]"

    monkeypatch.setattr("sable.clip.selector.call_claude_json", fake_claude)
    monkeypatch.setattr("sable.clip.selector.retry_with_backoff", lambda f: f())

    clips = [_make_clip(start=float(i * 30)) for i in range(21)]
    _evaluate_variants_batch(clips, segments=[], words=None)

    assert call_count[0] == 2, f"Expected 2 Claude calls for 21 clips, got {call_count[0]}"


def test_evaluate_variants_batch_kill_flag_removes_clip(monkeypatch):
    from sable.clip.selector import _evaluate_variants_batch

    ev_response = json.dumps([
        {"clip": 0, "chosen": "short", "kill": True, "kill_reason": "boring", "lands": True, "extend": False}
    ])

    monkeypatch.setattr("sable.clip.selector.call_claude_json", lambda *a, **kw: ev_response)
    monkeypatch.setattr("sable.clip.selector.retry_with_backoff", lambda f: f())

    clips = [_make_clip()]
    result = _evaluate_variants_batch(clips, segments=[], words=None)
    assert result == []


def test_evaluate_variants_batch_extend_searches_beyond_long_end(monkeypatch):
    from sable.clip.selector import _evaluate_variants_batch

    # Clip 0: extend=true, chosen="long" → end extended from 20.0 to 25.0
    # Clip 1: extend=true, chosen="short" → end NOT extended (stays at 110.0)
    # pause_after(25.0): before[-1].end=20.0, after[0].start=25.3 (>25.05) → pause=5.3 ≥ 0.2
    words = [
        {"start": 0.0, "end": 20.0, "text": "content"},
        {"start": 25.3, "end": 30.0, "text": "more"},
    ]
    segments = [
        {"start": 23.0, "end": 25.0, "text": "extended point."},
    ]

    ev_response = json.dumps([
        {"clip": 0, "chosen": "long",  "kill": False, "lands": True, "extend": True},
        {"clip": 1, "chosen": "short", "kill": False, "lands": True, "extend": True},
    ])

    monkeypatch.setattr("sable.clip.selector.call_claude_json", lambda *a, **kw: ev_response)
    monkeypatch.setattr("sable.clip.selector.retry_with_backoff", lambda f: f())

    clip0 = _make_clip(start=0.0,   short_end=10.0, medium_end=15.0, long_end=20.0)
    clip1 = _make_clip(start=100.0, short_end=110.0, medium_end=115.0, long_end=120.0)

    result = _evaluate_variants_batch([clip0, clip1], segments=segments, words=words, max_dur=90.0)

    assert len(result) == 2
    # clip 0: extended from 20.0 → 25.0
    assert result[0]["end"] == 25.0
    # clip 1: chosen="short", no extend despite extend=True
    assert result[1]["end"] == 110.0


def test_evaluate_variants_batch_handles_json_parse_failure_with_retry(monkeypatch):
    from sable.clip.selector import _evaluate_variants_batch

    valid_response = json.dumps([
        {"clip": 0, "chosen": "short", "kill": False, "lands": True, "extend": False, "reason": "ok"}
    ])
    call_results = iter(["invalid json {{{", valid_response])

    monkeypatch.setattr("sable.clip.selector.call_claude_json", lambda *a, **kw: next(call_results))
    monkeypatch.setattr("sable.clip.selector.retry_with_backoff", lambda f: f())

    clips = [_make_clip()]
    result = _evaluate_variants_batch(clips, segments=[], words=None)

    assert len(result) == 1
    assert result[0]["variant"] == "short"
