"""Tests for pulse/meta/recommender.py contract fixes."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_trend(trend_status="surging", confidence="A", current_lift=3.0):
    from sable.pulse.meta.trends import TrendResult
    from sable.pulse.meta.quality import EngagementQuality
    quality = EngagementQuality(
        confidence=confidence,
        confidence_reasons=[],
        sample_count=10,
        unique_authors=5,
        concentration=0.2,
        all_fallback=False,
        mixed_quality_warning="",
    )
    return TrendResult(
        format_bucket="short_clip",
        current_lift=current_lift,
        lift_vs_30d=2.5,
        lift_vs_7d=1.5,
        trend_status=trend_status,
        momentum="accelerating",
        confidence=confidence,
        confidence_reasons=[],
        quality=quality,
        reasons=[],
        gate_failures=[],
    )


def test_fatigue_penalty_fires_with_org():
    """Fatigue penalty should fire when posted_by entries have matching org field."""
    from sable.pulse.meta.recommender import compute_priority

    trend = _make_trend()
    org = "testorg"
    # Two entries with matching org — should trigger fatigue
    posted_by = [
        {"account": "@alice", "tweet_id": "1", "posted_at": "2026-03-01T00:00:00+00:00", "org": org},
        {"account": "@alice", "tweet_id": "2", "posted_at": "2026-03-02T00:00:00+00:00", "org": org},
    ]
    # No 'org' key in content — mirrors real vault note structure
    content = {"type": "clip", "topics": ["defi"], "posted_by": posted_by}

    score, reason = compute_priority(
        trend=trend,
        content=content,
        account_handle="@alice",
        vault_path=None,
        days_idle=0,
        org=org,  # passed explicitly, not read from content dict
    )
    # fatigue_penalty = max(2 * -2, 0) → -4, clamped to max(-4, -5) = -4
    assert "fatigue" in reason


def test_fatigue_penalty_fires_via_real_note_dict(tmp_path):
    """Fatigue fires when content is loaded from a vault note (no top-level org key)."""
    from sable.pulse.meta.recommender import compute_priority
    from sable.vault.notes import load_all_notes

    vault_path = tmp_path / "vault"
    content_dir = vault_path / "content"
    content_dir.mkdir(parents=True)

    org = "testorg"
    note_content = f"""---
id: clip-test
type: clip
topics:
  - defi
posted_by:
  - account: "@alice"
    tweet_id: "1"
    posted_at: "2026-03-01T00:00:00+00:00"
    org: {org}
  - account: "@alice"
    tweet_id: "2"
    posted_at: "2026-03-02T00:00:00+00:00"
    org: {org}
---

Body.
"""
    (content_dir / "clip-test.md").write_text(note_content, encoding="utf-8")

    notes = load_all_notes(vault_path)
    assert len(notes) == 1
    content = notes[0]
    # Vault notes do NOT have a top-level 'org' key
    assert "org" not in content

    trend = _make_trend()
    score, reason = compute_priority(
        trend=trend,
        content=content,
        account_handle="@alice",
        vault_path=None,
        days_idle=0,
        org=org,  # production path: org supplied by caller, not content dict
    )
    assert "fatigue" in reason


def test_build_recommendations_threads_org_for_fatigue(tmp_path):
    """build_recommendations() must pass org through to compute_priority — fatigue fires."""
    from sable.pulse.meta.recommender import build_recommendations

    vault_path = tmp_path / "vault"
    content_dir = vault_path / "content"
    content_dir.mkdir(parents=True)

    org = "testorg"
    # Note has posted_by entries with org but no top-level org key — real vault structure
    note_content = f"""---
id: clip-rec-test
type: clip
topics:
  - defi
posted_by:
  - account: "@alice"
    tweet_id: "1"
    posted_at: "2026-03-01T00:00:00+00:00"
    org: {org}
  - account: "@alice"
    tweet_id: "2"
    posted_at: "2026-03-02T00:00:00+00:00"
    org: {org}
---

Body.
"""
    (content_dir / "clip-rec-test.md").write_text(note_content, encoding="utf-8")

    # short_clip maps to content type "clip" — note will be matched
    trends = {"short_clip": _make_trend(trend_status="surging", confidence="A")}
    # String account works via getattr fallback in recommender
    accounts = ["@alice"]
    analysis = {"dominant_format_attrs": []}

    result = build_recommendations(
        trends=trends,
        accounts=accounts,
        vault_path=vault_path,
        analysis=analysis,
        org=org,
    )

    assert result["post_now"], "Expected at least one post_now recommendation"
    fatigue_recs = [r for r in result["post_now"] if "fatigue" in r.reason]
    assert fatigue_recs, (
        "Fatigue did not appear in any recommendation — "
        "org was not threaded through from build_recommendations() to compute_priority()"
    )


def test_days_since_last_post_uses_posted_at(tmp_path):
    """get_days_since_last_post should use 'posted_at' key, not 'date'."""
    from sable.pulse.meta.recommender import get_days_since_last_post

    vault_path = tmp_path / "vault"
    content_dir = vault_path / "content"
    content_dir.mkdir(parents=True)

    # Write a note with a posted_by entry using posted_at (14 days ago)
    old_date = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    note_content = f"""---
id: clip-1
type: clip
posted_by:
  - account: "@alice"
    tweet_id: "123"
    posted_at: "{old_date}"
    org: testorg
---

Body.
"""
    (content_dir / "clip-1.md").write_text(note_content, encoding="utf-8")

    days = get_days_since_last_post("@alice", vault_path)
    assert days >= 13  # should be approximately 14
