"""Tests for _assemble_bridge_section — bridge node activity injection."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from sable.platform.db import ensure_schema
from sable.pulse.meta.db import _SCHEMA as META_SCHEMA
from sable.advise.stage1 import _assemble_bridge_section


def _make_platform_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test')")
    conn.commit()
    return conn


def _make_meta_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(META_SCHEMA)
    return conn


def _add_bridge_node(conn, org_id, entity_id, display_name, twitter_handle=None):
    conn.execute(
        "INSERT INTO entities (entity_id, org_id, display_name, status) VALUES (?, ?, ?, 'active')",
        (entity_id, org_id, display_name),
    )
    conn.execute(
        "INSERT INTO entity_tags (entity_id, tag, is_current) VALUES (?, 'bridge_node', 1)",
        (entity_id,),
    )
    if twitter_handle:
        conn.execute(
            "INSERT INTO entity_handles (entity_id, platform, handle) VALUES (?, 'twitter', ?)",
            (entity_id, twitter_handle),
        )
    conn.commit()


def _add_tweet(conn, author, days_ago=0, total_lift=5.0):
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    tid = str(uuid.uuid4())[:12]
    conn.execute(
        """INSERT INTO scanned_tweets
           (tweet_id, org, author_handle, posted_at, text, total_lift,
            likes, replies, reposts, quotes, bookmarks)
           VALUES (?, 'testorg', ?, ?, 'test', ?, 10, 5, 3, 1, 0)""",
        (tid, author, ts, total_lift),
    )
    conn.commit()


def test_bridge_section_rendered():
    """Bridge nodes with recent activity produce section."""
    platform = _make_platform_conn()
    meta = _make_meta_conn()

    _add_bridge_node(platform, "testorg", "e1", "Alice", "@alice")
    for i in range(5):
        _add_tweet(meta, "@alice", days_ago=i, total_lift=3.0)

    result = _assemble_bridge_section("testorg", platform, meta)
    assert "Bridge Node Activity" in result
    assert "Alice" in result
    assert "@alice" in result
    assert "tweets" in result


def test_bridge_section_empty_no_bridge_nodes():
    """No bridge nodes → empty string."""
    platform = _make_platform_conn()
    meta = _make_meta_conn()

    result = _assemble_bridge_section("testorg", platform, meta)
    assert result == ""


def test_bridge_section_skipped_no_meta():
    """No meta_conn → empty string."""
    platform = _make_platform_conn()
    _add_bridge_node(platform, "testorg", "e1", "Alice", "@alice")

    result = _assemble_bridge_section("testorg", platform, None)
    assert result == ""


def test_bridge_section_no_twitter_handle():
    """Bridge node without Twitter handle → shows 'no handle' message."""
    platform = _make_platform_conn()
    meta = _make_meta_conn()
    _add_bridge_node(platform, "testorg", "e1", "Bob")  # No Twitter handle

    result = _assemble_bridge_section("testorg", platform, meta)
    assert "no Twitter handle" in result


def test_bridge_section_no_recent_activity():
    """Bridge node with no recent tweets → shows 'no recent activity'."""
    platform = _make_platform_conn()
    meta = _make_meta_conn()
    _add_bridge_node(platform, "testorg", "e1", "Charlie", "@charlie")
    # No tweets inserted

    result = _assemble_bridge_section("testorg", platform, meta)
    assert "no recent activity" in result


def test_bridge_section_meta_query_error():
    """meta.db query failure → graceful 'data unavailable' message."""
    platform = _make_platform_conn()
    _add_bridge_node(platform, "testorg", "e1", "Alice", "@alice")

    # Create a meta conn where scanned_tweets doesn't exist
    broken_meta = sqlite3.connect(":memory:")
    broken_meta.row_factory = sqlite3.Row

    result = _assemble_bridge_section("testorg", platform, broken_meta)
    assert "data unavailable" in result
