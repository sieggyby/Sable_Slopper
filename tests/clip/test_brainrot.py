"""Tests for sable.clip.brainrot — energy fallback, pick() preference logic."""
import random
import pytest


def test_pick_prefers_sources_long_enough_to_avoid_double_loop(tmp_path, monkeypatch):
    """clip_duration=60 → prefer source ≥ 30 (clip/2); 20s rejected, 40s preferred."""
    short_vid = tmp_path / "short.mp4"
    long_vid = tmp_path / "long.mp4"
    short_vid.write_bytes(b"x")
    long_vid.write_bytes(b"x")

    index = [
        {"path": str(short_vid), "energy": "medium", "duration": 20.0, "tags": []},
        {"path": str(long_vid),  "energy": "medium", "duration": 40.0, "tags": []},
    ]
    monkeypatch.setattr("sable.clip.brainrot.load_index", lambda: index)

    from sable.clip.brainrot import pick

    random.seed(42)
    results = {pick(energy="medium", clip_duration=60.0) for _ in range(100)}

    assert str(long_vid) in results
    assert str(short_vid) not in results


def test_pick_falls_back_to_any_candidate_when_none_long_enough(tmp_path, monkeypatch):
    """Only one 20s source; clip_duration=60 → preferred=[]; fallback returns it anyway."""
    vid = tmp_path / "only.mp4"
    vid.write_bytes(b"x")

    index = [{"path": str(vid), "energy": "medium", "duration": 20.0, "tags": []}]
    monkeypatch.setattr("sable.clip.brainrot.load_index", lambda: index)

    from sable.clip.brainrot import pick

    result = pick(energy="medium", clip_duration=60.0)
    assert result == str(vid)


@pytest.mark.parametrize("energy,expected", [
    ("low",    ["low", "medium"]),
    ("high",   ["high", "medium"]),
    ("medium", ["medium", "low", "high"]),
])
def test_pick_energy_fallback_order(energy, expected):
    from sable.clip.brainrot import _energy_fallback

    assert _energy_fallback(energy) == expected


def test_pick_returns_none_for_energy_none(monkeypatch):
    """pick(energy='none') returns None without ever calling load_index."""
    monkeypatch.setattr(
        "sable.clip.brainrot.load_index",
        lambda: (_ for _ in ()).throw(AssertionError("load_index must not be called")),
    )

    from sable.clip.brainrot import pick

    result = pick(energy="none")
    assert result is None


def test_pick_prefers_theme_matched_over_untagged(tmp_path, monkeypatch):
    """When tags=['defi'], prefer the defi-tagged source over untagged."""
    tagged = tmp_path / "defi.mp4"
    untagged = tmp_path / "generic.mp4"
    tagged.write_bytes(b"x")
    untagged.write_bytes(b"x")

    index = [
        {"path": str(untagged), "energy": "medium", "duration": 30.0, "tags": []},
        {"path": str(tagged),   "energy": "medium", "duration": 30.0, "tags": ["defi"]},
    ]
    monkeypatch.setattr("sable.clip.brainrot.load_index", lambda: index)

    from sable.clip.brainrot import pick

    random.seed(42)
    results = {pick(energy="medium", tags=["defi"]) for _ in range(50)}
    assert str(tagged) in results
    assert str(untagged) not in results


def test_pick_falls_back_to_untagged_when_no_theme_match(tmp_path, monkeypatch):
    """When tags=['gaming'] but no gaming source exists, falls back to untagged."""
    vid = tmp_path / "generic.mp4"
    vid.write_bytes(b"x")

    index = [
        {"path": str(vid), "energy": "medium", "duration": 30.0, "tags": ["defi"]},
    ]
    monkeypatch.setattr("sable.clip.brainrot.load_index", lambda: index)

    from sable.clip.brainrot import pick

    result = pick(energy="medium", tags=["gaming"])
    assert result == str(vid)


def test_pick_theme_plus_duration_preference(tmp_path, monkeypatch):
    """Theme-matched + long enough beats theme-matched + short."""
    short_themed = tmp_path / "short_defi.mp4"
    long_themed = tmp_path / "long_defi.mp4"
    short_themed.write_bytes(b"x")
    long_themed.write_bytes(b"x")

    index = [
        {"path": str(short_themed), "energy": "medium", "duration": 10.0, "tags": ["defi"]},
        {"path": str(long_themed),  "energy": "medium", "duration": 40.0, "tags": ["defi"]},
    ]
    monkeypatch.setattr("sable.clip.brainrot.load_index", lambda: index)

    from sable.clip.brainrot import pick

    random.seed(42)
    results = {pick(energy="medium", tags=["defi"], clip_duration=60.0) for _ in range(50)}
    assert str(long_themed) in results
    assert str(short_themed) not in results


def test_pick_no_tags_ignores_theme_layer(tmp_path, monkeypatch):
    """When no tags provided, both tagged and untagged are equally eligible."""
    tagged = tmp_path / "tagged.mp4"
    untagged = tmp_path / "untagged.mp4"
    tagged.write_bytes(b"x")
    untagged.write_bytes(b"x")

    index = [
        {"path": str(untagged), "energy": "medium", "duration": 30.0, "tags": []},
        {"path": str(tagged),   "energy": "medium", "duration": 30.0, "tags": ["defi"]},
    ]
    monkeypatch.setattr("sable.clip.brainrot.load_index", lambda: index)

    from sable.clip.brainrot import pick

    random.seed(42)
    results = {pick(energy="medium") for _ in range(100)}
    assert len(results) == 2  # both are eligible


def test_selector_threads_theme_tags():
    """_resolve_clip passes through theme_tags from selection."""
    from sable.clip.selector import _resolve_clip

    selection = {
        "windows": [0],
        "reason": "test",
        "hook": "hook",
        "caption_hint": "hint",
        "score": 8,
        "theme_tags": ["defi", "regulation"],
    }
    windows = [{"start": 0.0, "end": 30.0, "text": "test"}]
    segments = [{"text": "This is a test.", "start": 0.0, "end": 15.0}]
    words = [
        {"text": "This", "start": 0.0, "end": 0.5},
        {"text": "test.", "start": 14.0, "end": 15.0},
    ]
    result = _resolve_clip(selection, windows, words, segments)
    assert result is not None
    assert result["theme_tags"] == ["defi", "regulation"]
