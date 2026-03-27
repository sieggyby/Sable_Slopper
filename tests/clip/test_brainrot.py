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
