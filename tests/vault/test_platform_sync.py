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
