"""Tests for the advise stage1, stage2, fallback, and generate modules."""
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sable.advise.stage1 import assemble_input, render_summary, _compute_lift, _read_profile_file
from sable.advise.template_fallback import render_fallback
from sable.advise.stage2 import build_system_prompt, OUTPUT_FORMAT_CONTRACT


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _make_assembled_base(org_id="testorg", handle="alice"):
    """Return a minimal assembled dict as if assemble_input returned it."""
    return {
        "handle": handle,
        "org_id": org_id,
        "profile": {
            "tone": "casual, witty",
            "interests": "DeFi, crypto",
            "context": "crypto KOL account",
            "notes": "(not configured)",
        },
        "posts": [],
        "post_freshness": None,
        "pulse_available": False,
        "topics": [],
        "formats": [],
        "meta_scan_date": None,
        "meta_available": False,
        "meta_stale": False,
        "entities": [],
        "content_items": [],
        "tracking_last_sync": None,
        "data_freshness": {
            "pulse_last_track": None,
            "meta_last_scan": None,
            "tracking_last_sync": None,
        },
        "median_engagement": 0,
    }


def _make_post(text="test post", engagement=100.0, content_type="tweet",
               posted_at="2026-03-20T12:00:00", lift=1.0):
    return {
        "id": uuid.uuid4().hex,
        "text": text,
        "posted_at": posted_at,
        "content_type": content_type,
        "engagement": engagement,
        "lift": lift,
        "taken_at": posted_at,
    }


# ─────────────────────────────────────────────────────────────────────
# Test 1: assemble_input returns expected keys
# ─────────────────────────────────────────────────────────────────────

def test_assemble_input_returns_all_keys(conn, tmp_path, monkeypatch):
    """assemble_input returns all expected top-level keys."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    result = assemble_input("alice", "testorg", conn)

    required_keys = [
        "handle", "org_id", "profile", "posts", "post_freshness",
        "pulse_available", "topics", "formats", "meta_available",
        "entities", "content_items", "data_freshness",
    ]
    for key in required_keys:
        assert key in result, f"Missing key: {key}"


# ─────────────────────────────────────────────────────────────────────
# Test 2: profile files read correctly
# ─────────────────────────────────────────────────────────────────────

def test_read_profile_file_existing(tmp_path):
    """Profile file content is read correctly when file exists."""
    handle_dir = tmp_path / "profiles" / "alice"
    handle_dir.mkdir(parents=True)
    (handle_dir / "tone.md").write_text("witty and direct")

    result = _read_profile_file(handle_dir, "tone.md")
    assert result == "witty and direct"


def test_read_profile_file_missing(tmp_path):
    """Missing profile file returns '(not configured)'."""
    handle_dir = tmp_path / "profiles" / "noone"
    result = _read_profile_file(handle_dir, "tone.md")
    assert result == "(not configured)"


# ─────────────────────────────────────────────────────────────────────
# Test 3: compute_lift formula
# ─────────────────────────────────────────────────────────────────────

def test_compute_lift_formula():
    """Lift formula: likes*1 + replies*3 + retweets*4 + quotes*5 + bookmarks*2 + views*0.5."""
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "likes": 10, "replies": 2, "retweets": 3, "quotes": 1,
        "bookmarks": 5, "views": 100
    }.get(k, 0)
    result = _compute_lift(row)
    expected = 10*1.0 + 2*3.0 + 3*4.0 + 1*5.0 + 5*2.0 + 100*0.5
    assert result == expected


# ─────────────────────────────────────────────────────────────────────
# Test 4: render_summary with no data shows freshness section
# ─────────────────────────────────────────────────────────────────────

def test_render_summary_no_data():
    """render_summary with no posts/topics shows Data Freshness section."""
    data = _make_assembled_base()
    result = render_summary(data)

    assert "## Account Profile" in result
    assert "## Data Freshness" in result
    assert "pulse_last_track" in result


# ─────────────────────────────────────────────────────────────────────
# Test 5: render_summary with posts shows performance section
# ─────────────────────────────────────────────────────────────────────

def test_render_summary_with_posts():
    """render_summary with >= 5 posts shows Post Performance section."""
    data = _make_assembled_base()
    data["pulse_available"] = True
    data["median_engagement"] = 100.0
    data["posts"] = [
        _make_post(f"post {i}", engagement=100.0 * (i + 1), lift=float(i + 1))
        for i in range(7)
    ]
    result = render_summary(data)

    assert "## Post Performance" in result
    assert "Top 5 by lift" in result


# ─────────────────────────────────────────────────────────────────────
# Test 6: render_summary stale pulse shows stale message
# ─────────────────────────────────────────────────────────────────────

def test_render_summary_stale_pulse():
    """Stale pulse data shows stale notice, not post performance."""
    data = _make_assembled_base()
    data["pulse_available"] = False
    data["data_freshness"]["pulse_last_track"] = "2025-01-01T00:00:00"

    result = render_summary(data)
    assert "stale" in result.lower() or "Performance" in result


# ─────────────────────────────────────────────────────────────────────
# Test 7: render_summary with topics shows trend section
# ─────────────────────────────────────────────────────────────────────

def test_render_summary_with_topics():
    """Topics with surging acceleration appear in trend section."""
    data = _make_assembled_base()
    data["meta_available"] = True
    data["topics"] = [
        {"term": "DeFi yields", "avg_lift": 2.5, "acceleration": 0.5, "unique_authors": 5, "mention_count": 20},
    ]
    result = render_summary(data)

    assert "## Pulse Meta Trends" in result
    assert "DeFi yields" in result


# ─────────────────────────────────────────────────────────────────────
# Test 8: render_summary with entities shows entity graph
# ─────────────────────────────────────────────────────────────────────

def test_render_summary_with_entities():
    """Entities appear in Entity Graph section."""
    data = _make_assembled_base()
    data["entities"] = [
        {
            "entity_id": "eid1",
            "display_name": "TopFan",
            "status": "active",
            "handles": [{"platform": "twitter", "handle": "topfan"}],
            "tags": ["cultist_candidate"],
        }
    ]
    result = render_summary(data)

    assert "## Entity Graph" in result
    assert "TopFan" in result


# ─────────────────────────────────────────────────────────────────────
# Test 9: template fallback renders all sections when data present
# ─────────────────────────────────────────────────────────────────────

def test_template_fallback_renders_sections():
    """Template fallback renders posts, topics, entities, content when available."""
    data = _make_assembled_base()
    data["posts"] = [_make_post("best tweet", lift=3.0)]
    data["topics"] = [{"term": "layer2", "avg_lift": 2.0}]
    data["entities"] = [
        {
            "display_name": "Alice",
            "handles": [{"platform": "twitter", "handle": "alice"}],
            "tags": ["bridge_node"],
        }
    ]
    data["content_items"] = [
        {"content_type": "tweet", "body": "community post", "created_at": "2026-03-20T00:00:00"}
    ]

    result = render_fallback(data, "budget exceeded")

    assert "budget exceeded" in result
    assert "best tweet" in result
    assert "layer2" in result
    assert "Alice" in result
    assert "community post" in result


# ─────────────────────────────────────────────────────────────────────
# Test 10: template fallback caps at 3000 chars
# ─────────────────────────────────────────────────────────────────────

def test_template_fallback_caps_length():
    """Template fallback output is capped at 3000 characters."""
    data = _make_assembled_base()
    data["posts"] = [_make_post("x" * 200, lift=float(i)) for i in range(50)]
    data["topics"] = [{"term": f"topic_{i}", "avg_lift": float(i)} for i in range(50)]

    result = render_fallback(data, "test")
    assert len(result) <= 3000


# ─────────────────────────────────────────────────────────────────────
# Test 11: build_system_prompt includes all profile sections
# ─────────────────────────────────────────────────────────────────────

def test_build_system_prompt_includes_all_sections():
    """build_system_prompt includes tone, interests, context, notes, and format contract."""
    profile = {
        "tone": "aggressive",
        "interests": "NFTs",
        "context": "NFT project community manager",
        "notes": "avoid rugs",
    }
    prompt = build_system_prompt(profile)

    assert "aggressive" in prompt
    assert "NFTs" in prompt
    assert "NFT project community manager" in prompt
    assert "avoid rugs" in prompt
    assert OUTPUT_FORMAT_CONTRACT in prompt


# ─────────────────────────────────────────────────────────────────────
# Test 12: assemble_input with sable.db entities
# ─────────────────────────────────────────────────────────────────────

def test_assemble_input_loads_entities(conn, tmp_path, monkeypatch):
    """assemble_input loads entities with priority tags from sable.db."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    # Insert entity with cultist_candidate tag
    eid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO entities (entity_id, org_id, display_name, status) VALUES (?, 'testorg', 'TopFan', 'active')",
        (eid,)
    )
    conn.execute(
        "INSERT INTO entity_handles (entity_id, platform, handle) VALUES (?, 'twitter', 'topfan')",
        (eid,)
    )
    conn.execute(
        "INSERT INTO entity_tags (entity_id, tag, confidence, is_current) VALUES (?, 'cultist_candidate', 0.9, 1)",
        (eid,)
    )
    conn.commit()

    result = assemble_input("alice", "testorg", conn)

    assert len(result["entities"]) >= 1
    assert any(e["display_name"] == "TopFan" for e in result["entities"])


# ─────────────────────────────────────────────────────────────────────
# Test 13: assemble_input with content_items (source_tool filter)
# ─────────────────────────────────────────────────────────────────────

def test_assemble_input_content_items_filtered(conn, tmp_path, monkeypatch):
    """assemble_input only loads content_items with source_tool=sable_tracking."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    # Insert tracking item
    item_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO content_items (item_id, org_id, content_type, body, metadata_json, created_at)
           VALUES (?, 'testorg', 'tweet', 'tracking post', ?, ?)""",
        (item_id, json.dumps({"source_tool": "sable_tracking"}), created_at)
    )
    # Insert non-tracking item (should be filtered)
    item_id2 = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO content_items (item_id, org_id, content_type, body, metadata_json, created_at)
           VALUES (?, 'testorg', 'tweet', 'other post', '{}', ?)""",
        (item_id2, created_at)
    )
    conn.commit()

    result = assemble_input("alice", "testorg", conn)
    assert any(c["body"] == "tracking post" for c in result["content_items"])
    assert not any(c["body"] == "other post" for c in result["content_items"])


# ─────────────────────────────────────────────────────────────────────
# Test 14: assemble_input tracking_last_sync reads from sync_runs
# ─────────────────────────────────────────────────────────────────────

def test_assemble_input_tracking_sync_freshness(conn, tmp_path, monkeypatch):
    """assemble_input reads tracking_last_sync from sync_runs with sync_type='sable_tracking'."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    conn.execute(
        """INSERT INTO sync_runs (org_id, sync_type, status, completed_at)
           VALUES ('testorg', 'sable_tracking', 'completed', '2026-03-20T10:00:00')"""
    )
    conn.commit()

    result = assemble_input("alice", "testorg", conn)
    assert result["data_freshness"]["tracking_last_sync"] == "2026-03-20T10:00:00"


# ─────────────────────────────────────────────────────────────────────
# Test 15: render_summary with 10+ posts shows worst format
# ─────────────────────────────────────────────────────────────────────

def test_render_summary_worst_format_with_10_posts():
    """With >= 10 posts, the worst format appears in the summary."""
    data = _make_assembled_base()
    data["pulse_available"] = True
    data["median_engagement"] = 100.0
    # Mix of formats: 8 'clip' with high lift, 3 'image' with low lift
    posts = [_make_post(f"clip post {i}", content_type="clip", lift=2.0) for i in range(8)]
    posts += [_make_post(f"image post {i}", content_type="image", lift=0.3) for i in range(3)]
    data["posts"] = posts
    result = render_summary(data)

    assert "Worst format" in result
    assert "image" in result


# ─────────────────────────────────────────────────────────────────────
# Test 16: assemble_input pulse not available when DB missing
# ─────────────────────────────────────────────────────────────────────

def test_assemble_input_pulse_not_available_when_missing(conn, tmp_path, monkeypatch):
    """pulse_available=False when pulse.db doesn't exist."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    result = assemble_input("alice", "testorg", conn)
    assert result["pulse_available"] is False
    assert result["posts"] == []
