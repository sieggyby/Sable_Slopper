"""Tests for clip selector dry-run logic."""
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

    clips = select_clips(transcript, acc, num_clips=2, dry_run=True)
    assert len(clips) == 1  # dry run returns 1 clip
    assert clips[0]["reason"] == "DRY RUN — first 30s"
    assert clips[0]["start"] == 0.0


def test_selector_respects_max_duration():
    from sable.roster.models import Account
    from sable.clip.selector import select_clips

    acc = Account(handle="@test")
    transcript = {"text": "test", "segments": []}

    clips = select_clips(transcript, acc, max_duration=20.0, dry_run=True)
    assert clips[0]["end"] <= 20.0
