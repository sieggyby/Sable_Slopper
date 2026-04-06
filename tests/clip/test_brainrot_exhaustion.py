"""AQ-16: Brainrot source exhaustion test."""
from __future__ import annotations


def test_pick_empty_index_returns_none(monkeypatch):
    """pick() with empty index returns None."""
    monkeypatch.setattr("sable.clip.brainrot.load_index", lambda: [])

    from sable.clip.brainrot import pick

    result = pick(energy="medium")
    assert result is None


def test_pick_no_matching_energy_returns_none(monkeypatch):
    """pick() with no files matching any fallback energy returns None."""
    # Index has only 'low' energy files, but all files don't exist
    monkeypatch.setattr("sable.clip.brainrot.load_index", lambda: [
        {"path": "/nonexistent/video.mp4", "energy": "low", "duration": 30.0, "tags": []},
    ])

    from sable.clip.brainrot import pick

    # Picks with 'high' — fallback order is ['high', 'medium'],
    # so 'low' files won't match. But the file also doesn't exist so
    # it gets filtered out. Result: None.
    result = pick(energy="high")
    assert result is None


def test_pick_all_files_missing_returns_none(tmp_path, monkeypatch):
    """pick() when all indexed files are missing from disk returns None."""
    monkeypatch.setattr("sable.clip.brainrot.load_index", lambda: [
        {"path": str(tmp_path / "gone1.mp4"), "energy": "medium", "duration": 30.0, "tags": []},
        {"path": str(tmp_path / "gone2.mp4"), "energy": "medium", "duration": 30.0, "tags": []},
    ])

    from sable.clip.brainrot import pick

    result = pick(energy="medium")
    assert result is None
