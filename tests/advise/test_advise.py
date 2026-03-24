"""Tests for the advise stage1, stage2, fallback, and generate modules."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from sable.advise.stage1 import assemble_input, render_summary, _compute_lift, _read_profile_file
from sable.advise.template_fallback import render_fallback
from sable.advise.stage2 import build_system_prompt, OUTPUT_FORMAT_CONTRACT
import sable.advise.stage2 as _stage2


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


# ─────────────────────────────────────────────────────────────────────
# T2a: assemble_input marks data_quality.pulse_ok=False when pulse unavailable
# ─────────────────────────────────────────────────────────────────────

def test_assemble_input_pulse_failure_marks_degraded(conn, tmp_path, monkeypatch):
    """data_quality.pulse_ok is False when pulse.db does not exist."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)
    # pulse.db is absent from tmp_path — _open_db_readonly returns None

    result = assemble_input("alice", "testorg", conn)
    assert "data_quality" in result
    assert result["data_quality"]["pulse_ok"] is False


# ─────────────────────────────────────────────────────────────────────
# T2b: generate_advise sets stale=1 in artifact when pulse is unavailable
# ─────────────────────────────────────────────────────────────────────

def test_generate_marks_stale_when_pulse_unavailable(conn, tmp_path, monkeypatch):
    """artifact row has stale=1 when data_quality.pulse_ok=False."""
    from sable.advise.generate import generate_advise
    from sable.roster.models import Account, Persona, ContentSettings

    mock_account = Account(handle="alice", org="testorg", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    monkeypatch.setattr("sable.roster.manager.load_roster", lambda: {"alice": mock_account})
    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr("sable.advise.generate.check_budget", lambda *a, **kw: None)
    monkeypatch.setattr(
        "sable.shared.paths.vault_dir",
        lambda org="": tmp_path / "vault" / (org or "default"),
    )

    degraded = _make_assembled_base()
    degraded["data_quality"] = {"pulse_ok": False, "meta_ok": True, "platform_ok": True}
    monkeypatch.setattr("sable.advise.generate.assemble_input", lambda *a, **kw: degraded)
    monkeypatch.setattr("sable.advise.generate.synthesize",
                        lambda *a, **kw: ("brief body", 0.001, 10, 5))

    import sable.config as sable_cfg
    monkeypatch.setattr(sable_cfg, "load_config", lambda: {
        "platform": {"cost_caps": {"max_ai_usd_per_strategy_brief": 1.00}, "degrade_mode": "fallback"}
    })

    generate_advise("alice")

    row = conn.execute(
        "SELECT stale FROM artifacts WHERE org_id='testorg' AND artifact_type='twitter_strategy_brief'"
    ).fetchone()
    assert row is not None, "Expected artifact row to be inserted"
    assert row["stale"] == 1, f"Expected stale=1 when pulse_ok=False, got stale={row['stale']}"


# ─────────────────────────────────────────────────────────────────────
# T3: stage2.synthesize uses the shared Claude wrapper
# ─────────────────────────────────────────────────────────────────────

def test_stage2_uses_shared_wrapper(monkeypatch):
    """synthesize() routes through the shared Claude wrapper and forwards org context."""
    wrapper_calls = []

    def fake_call_claude_with_usage(prompt, **kwargs):
        wrapper_calls.append({"prompt": prompt, **kwargs})
        return SimpleNamespace(
            text="response text",
            cost_usd=0.00105,
            input_tokens=100,
            output_tokens=50,
        )

    monkeypatch.setattr(_stage2, "call_claude_with_usage", fake_call_claude_with_usage)

    from sable.advise.stage2 import synthesize
    result = synthesize(
        "system prompt",
        "user summary",
        model="claude-sonnet-4-20250514",
        org_id="testorg",
    )

    assert result == ("response text", 0.00105, 100, 50)
    assert wrapper_calls == [{
        "prompt": "user summary",
        "system": "system prompt",
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "org_id": "testorg",
        "call_type": "advise",
    }]


def test_generate_advise_passes_org_id_to_synthesize(conn, tmp_path, monkeypatch):
    """generate_advise() passes account org_id into stage2 synthesis."""
    from sable.advise.generate import generate_advise
    from sable.roster.models import Account, Persona, ContentSettings

    mock_account = Account(handle="alice", org="testorg", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    monkeypatch.setattr("sable.roster.manager.load_roster", lambda: {"alice": mock_account})
    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr("sable.advise.generate.check_budget", lambda *a, **kw: None)
    monkeypatch.setattr(
        "sable.shared.paths.vault_dir",
        lambda org="": tmp_path / "vault" / (org or "default"),
    )

    assembled = _make_assembled_base()
    assembled["pulse_available"] = True
    assembled["data_quality"] = {"pulse_ok": True, "meta_ok": True, "platform_ok": True}
    monkeypatch.setattr("sable.advise.generate.assemble_input", lambda *a, **kw: assembled)

    synthesize_calls = []

    def fake_synthesize(system_prompt, assembled_summary, model="claude-sonnet-4-20250514",
                        max_tokens=1500, org_id=None):
        synthesize_calls.append({
            "system_prompt": system_prompt,
            "assembled_summary": assembled_summary,
            "model": model,
            "max_tokens": max_tokens,
            "org_id": org_id,
        })
        return "brief body", 0.001, 10, 5

    monkeypatch.setattr("sable.advise.generate.synthesize", fake_synthesize)

    import sable.config as sable_cfg
    monkeypatch.setattr(sable_cfg, "load_config", lambda: {
        "platform": {"cost_caps": {"max_ai_usd_per_strategy_brief": 1.00}, "degrade_mode": "fallback"}
    })

    generate_advise("alice")

    assert len(synthesize_calls) == 1
    assert synthesize_calls[0]["org_id"] == "testorg"


# ─────────────────────────────────────────────────────────────────────
# T4: generate_advise raises BRIEF_CAP_EXCEEDED when estimated cost exceeds cap
# ─────────────────────────────────────────────────────────────────────

def test_generate_raises_when_brief_cost_exceeds_cap(conn, tmp_path, monkeypatch):
    """SableError(BRIEF_CAP_EXCEEDED) raised when estimated cost > per-brief cap."""
    from sable.advise.generate import generate_advise
    from sable.platform.errors import SableError
    from sable.roster.models import Account, Persona, ContentSettings

    mock_account = Account(handle="alice", org="testorg", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    monkeypatch.setattr("sable.roster.manager.load_roster", lambda: {"alice": mock_account})
    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr("sable.advise.generate.check_budget", lambda *a, **kw: None)
    monkeypatch.setattr(
        "sable.shared.paths.vault_dir",
        lambda org="": tmp_path / "vault" / (org or "default"),
    )

    # Large assembled input so render_summary produces enough tokens to exceed a tiny cap
    large_assembled = _make_assembled_base()
    large_assembled["pulse_available"] = True
    large_assembled["posts"] = [
        _make_post("x" * 200, lift=float(i)) for i in range(20)
    ]
    large_assembled["data_quality"] = {"pulse_ok": True, "meta_ok": True, "platform_ok": True}
    monkeypatch.setattr("sable.advise.generate.assemble_input", lambda *a, **kw: large_assembled)

    # Tiny cap that any non-trivial summary will exceed
    import sable.config as sable_cfg
    monkeypatch.setattr(sable_cfg, "load_config", lambda: {
        "platform": {"cost_caps": {"max_ai_usd_per_strategy_brief": 0.000001}, "degrade_mode": "fallback"}
    })

    with pytest.raises(SableError) as exc_info:
        generate_advise("alice")

    assert exc_info.value.code == "BRIEF_CAP_EXCEEDED"


# ─────────────────────────────────────────────────────────────────────
# AR-3a: assemble_input marks platform_ok=False when content_items query fails
# ─────────────────────────────────────────────────────────────────────

def test_assemble_input_content_items_failure_marks_platform_degraded(conn, tmp_path, monkeypatch):
    """data_quality.platform_ok is False when content_items query raises."""
    import sqlite3 as _sqlite3
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)

    class _FailOnContentItems:
        def __init__(self, real_conn):
            self._real = real_conn
            self.row_factory = real_conn.row_factory

        def execute(self, sql, *args, **kwargs):
            if "content_items" in sql:
                raise _sqlite3.OperationalError("injected failure")
            return self._real.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._real, name)

    result = assemble_input("alice", "testorg", _FailOnContentItems(conn))
    assert result["data_quality"]["platform_ok"] is False


# ─────────────────────────────────────────────────────────────────────
# AR-3b: generate_advise sets degraded=1 in artifact when platform_ok=False
# ─────────────────────────────────────────────────────────────────────

def test_generate_marks_degraded_when_platform_unavailable(conn, tmp_path, monkeypatch):
    """artifact row has degraded=1 when data_quality.platform_ok=False."""
    import yaml
    from sable.advise.generate import generate_advise
    from sable.roster.models import Account, Persona, ContentSettings

    mock_account = Account(handle="alice", org="testorg", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    monkeypatch.setattr("sable.roster.manager.load_roster", lambda: {"alice": mock_account})
    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr("sable.advise.generate.check_budget", lambda *a, **kw: None)
    monkeypatch.setattr(
        "sable.shared.paths.vault_dir",
        lambda org="": tmp_path / "vault" / (org or "default"),
    )

    platform_degraded = _make_assembled_base()
    platform_degraded["data_quality"] = {"pulse_ok": True, "meta_ok": True, "platform_ok": False}
    monkeypatch.setattr("sable.advise.generate.assemble_input", lambda *a, **kw: platform_degraded)
    monkeypatch.setattr("sable.advise.generate.synthesize",
                        lambda *a, **kw: ("brief body", 0.001, 10, 5))

    import sable.config as sable_cfg
    monkeypatch.setattr(sable_cfg, "load_config", lambda: {
        "platform": {"cost_caps": {"max_ai_usd_per_strategy_brief": 1.00}, "degrade_mode": "fallback"}
    })

    generate_advise("alice")

    row = conn.execute(
        "SELECT stale, degraded FROM artifacts WHERE org_id='testorg' AND artifact_type='twitter_strategy_brief'"
    ).fetchone()
    assert row is not None, "Expected artifact row to be inserted"
    assert row["stale"] == 0, f"Expected stale=0, got {row['stale']}"
    assert row["degraded"] == 1, f"Expected degraded=1 when platform_ok=False, got {row['degraded']}"

    content = (tmp_path / "vault" / "testorg" / "playbooks" / "twitter_alice.md").read_text()
    fm_end = content.index("---", 4)
    fm = yaml.safe_load(content[4:fm_end])
    assert fm["degraded"] is True, f"Expected degraded=true in frontmatter, got {fm.get('degraded')}"


# ─────────────────────────────────────────────────────────────────────
# NEW: generate.py partial-write recovery tests
# ─────────────────────────────────────────────────────────────────────

def _setup_generate_mocks(monkeypatch, conn, tmp_path, assembled_override=None):
    """Common setup for generate_advise tests."""
    from sable.advise.generate import generate_advise  # noqa: F401
    from sable.roster.models import Account, Persona, ContentSettings
    import sable.config as sable_cfg

    mock_account = Account(handle="alice", org="testorg", display_name="Alice",
                           persona=Persona(), content=ContentSettings())
    monkeypatch.setattr("sable.roster.manager.load_roster", lambda: {"alice": mock_account})
    monkeypatch.setattr("sable.advise.generate.get_db", lambda: conn)
    monkeypatch.setattr("sable.advise.generate.check_budget", lambda *a, **kw: None)
    monkeypatch.setattr(
        "sable.shared.paths.vault_dir",
        lambda org="": tmp_path / "vault" / (org or "default"),
    )
    assembled = assembled_override or _make_assembled_base()
    if "data_quality" not in assembled:
        assembled["data_quality"] = {"pulse_ok": True, "meta_ok": True, "platform_ok": True}
    monkeypatch.setattr("sable.advise.generate.assemble_input", lambda *a, **kw: assembled)
    monkeypatch.setattr("sable.advise.generate.synthesize",
                        lambda *a, **kw: ("brief body", 0.001, 10, 5))
    monkeypatch.setattr(sable_cfg, "load_config", lambda: {
        "platform": {"cost_caps": {"max_ai_usd_per_strategy_brief": 1.00}, "degrade_mode": "fallback"}
    })


class _FailAfterNConn:
    """sqlite3.Connection wrapper that raises OperationalError on commit() after N calls."""

    def __init__(self, real_conn, fail_after: int = 1):
        self._c = real_conn
        self._commits = 0
        self._fail_after = fail_after
        self.row_factory = real_conn.row_factory

    def execute(self, *a, **kw):
        return self._c.execute(*a, **kw)

    def executescript(self, *a, **kw):
        return self._c.executescript(*a, **kw)

    def commit(self):
        self._commits += 1
        if self._commits > self._fail_after:
            raise sqlite3.OperationalError("injected commit failure")
        return self._c.commit()

    def close(self):
        return self._c.close()

    def __getattr__(self, name):
        return getattr(self._c, name)


def test_generate_db_failure_restores_prior_file(conn, tmp_path, monkeypatch):
    """When conn.commit() raises, prior brief file content is restored."""
    from sable.advise.generate import generate_advise

    failing_conn = _FailAfterNConn(conn, fail_after=1)
    _setup_generate_mocks(monkeypatch, failing_conn, tmp_path)
    monkeypatch.setattr("sable.advise.generate.get_db", lambda: failing_conn)

    # Create a prior brief at the expected path
    playbooks_dir = tmp_path / "vault" / "testorg" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    prior_path = playbooks_dir / "twitter_alice.md"
    prior_content = "---\nprior: true\n---\n\nPrior brief content.\n"
    prior_path.write_text(prior_content, encoding="utf-8")

    with pytest.raises(sqlite3.OperationalError):
        generate_advise("alice")

    # Prior content must be restored
    assert prior_path.exists(), "File should still exist after rollback"
    assert prior_path.read_text(encoding="utf-8") == prior_content, "Prior content should be restored"

    # No temp or bak files remain
    assert not prior_path.with_suffix(".md.tmp").exists(), ".md.tmp should be cleaned up"
    assert not prior_path.with_suffix(".md.bak").exists(), ".md.bak should be cleaned up"


def test_generate_no_prior_db_failure_leaves_no_file(conn, tmp_path, monkeypatch):
    """When no prior file exists and conn.commit() raises, out_path does not remain."""
    from sable.advise.generate import generate_advise

    failing_conn = _FailAfterNConn(conn, fail_after=1)
    _setup_generate_mocks(monkeypatch, failing_conn, tmp_path)
    monkeypatch.setattr("sable.advise.generate.get_db", lambda: failing_conn)

    out_path = tmp_path / "vault" / "testorg" / "playbooks" / "twitter_alice.md"
    assert not out_path.exists()

    with pytest.raises(sqlite3.OperationalError):
        generate_advise("alice")

    assert not out_path.exists(), "No file should remain when no prior existed and DB failed"
    assert not out_path.with_suffix(".md.tmp").exists()
    assert not out_path.with_suffix(".md.bak").exists()


def test_generate_data_caveats_block_when_stale(conn, tmp_path, monkeypatch):
    """Data Caveats block appears in generated brief when pulse_ok=False."""
    from sable.advise.generate import generate_advise

    assembled = _make_assembled_base()
    assembled["data_quality"] = {"pulse_ok": False, "meta_ok": True, "platform_ok": True}
    _setup_generate_mocks(monkeypatch, conn, tmp_path, assembled_override=assembled)

    result = generate_advise("alice")

    content = Path(result).read_text(encoding="utf-8")
    assert "## Data Caveats" in content, "Data Caveats section should appear when pulse_ok=False"
    assert "Pulse performance data" in content


def test_generate_no_caveats_when_healthy(conn, tmp_path, monkeypatch):
    """No Data Caveats block when all data_quality flags are True."""
    from sable.advise.generate import generate_advise

    assembled = _make_assembled_base()
    assembled["data_quality"] = {"pulse_ok": True, "meta_ok": True, "platform_ok": True}
    _setup_generate_mocks(monkeypatch, conn, tmp_path, assembled_override=assembled)

    result = generate_advise("alice")

    content = Path(result).read_text(encoding="utf-8")
    assert "## Data Caveats" not in content, "No Data Caveats section when all flags healthy"
