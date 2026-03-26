"""Tests for platform_sync._build_entity_note source_time handling."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta


def _make_entity(entity_id="e1", display_name="Test User", status="active"):
    return {
        "entity_id": entity_id,
        "display_name": display_name,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _make_content_item(created_at=None, source_time=None, body="test body"):
    return {
        "content_type": "tweet",
        "body": body,
        "created_at": created_at,
        "source_time": source_time,
        "url": None,
    }


def test_build_entity_note_uses_source_time_for_filter():
    """Items should be included/excluded based on source_time, not created_at."""
    from sable.vault.platform_sync import _build_entity_note

    now = datetime.now(timezone.utc)

    # Item A: created_at is recent (5d ago), source_time is old (95d ago) → excluded
    item_a = _make_content_item(
        created_at=(now - timedelta(days=5)).isoformat(),
        source_time=(now - timedelta(days=95)).isoformat(),
        body="item A body",
    )
    # Item B: created_at is old (95d ago), source_time is recent (5d ago) → included
    item_b = _make_content_item(
        created_at=(now - timedelta(days=95)).isoformat(),
        source_time=(now - timedelta(days=5)).isoformat(),
        body="item B body",
    )

    entity = _make_entity()
    result = _build_entity_note(entity, [], [], [], [item_a, item_b], [], "testorg")

    assert "item B body" in result
    assert "item A body" not in result


def test_build_entity_note_renders_source_time_not_created_at():
    """The rendered content line should display source_time, not created_at."""
    from sable.vault.platform_sync import _build_entity_note

    now = datetime.now(timezone.utc)
    source_time = (now - timedelta(days=5)).isoformat()
    created_at = (now - timedelta(days=2)).isoformat()

    item = _make_content_item(
        created_at=created_at,
        source_time=source_time,
        body="test body",
    )

    entity = _make_entity()
    result = _build_entity_note(entity, [], [], [], [item], [], "testorg")

    assert source_time in result
    assert created_at not in result


def test_build_entity_note_tag_lines_not_multiplied_by_runs():
    """2 tags × 3 diag runs must produce exactly 2 tag-mention lines, not 6."""
    from sable.vault.platform_sync import _build_entity_note
    entity = {"entity_id": "e1", "display_name": "Alice", "status": "active", "updated_at": None}
    handles = [{"platform": "twitter", "handle": "@alice"}]
    tags = [
        {"tag": "top_contributor", "confidence": 0.9, "source": "auto", "added_at": "2026-03-01"},
        {"tag": "bridge_node", "confidence": 0.7, "source": "auto", "added_at": "2026-03-02"},
    ]
    diag_runs = [
        {"result_json": "{}", "run_date": "2026-03-10", "started_at": "2026-03-10T00:00:00", "overall_grade": "A"},
        {"result_json": "{}", "run_date": "2026-03-17", "started_at": "2026-03-17T00:00:00", "overall_grade": "B"},
        {"result_json": "{}", "run_date": "2026-03-24", "started_at": "2026-03-24T00:00:00", "overall_grade": "A"},
    ]
    note = _build_entity_note(entity, handles, tags, [], [], diag_runs, "testorg")
    tag_lines = [ln for ln in note.splitlines() if "Tagged as" in ln and "score:" in ln]
    assert len(tag_lines) == 2, f"Expected 2 tag-mention lines, got {len(tag_lines)}: {tag_lines}"
