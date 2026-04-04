"""Tests for sable/calendar/planner.py — Slices A and B."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sable.calendar.planner import (
    CalendarDay,
    CalendarPlan,
    CalendarSlot,
    _get_format_trends,
    _get_posting_history,
    _get_vault_inventory,
    render_calendar,
)


# ---------------------------------------------------------------------------
# Schema helpers (reuse pulse pattern)
# ---------------------------------------------------------------------------

_PULSE_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    account_handle TEXT NOT NULL,
    platform TEXT DEFAULT 'twitter',
    url TEXT,
    text TEXT,
    posted_at TEXT,
    sable_content_type TEXT,
    sable_content_path TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    taken_at TEXT DEFAULT (datetime('now')),
    likes INTEGER DEFAULT 0,
    retweets INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    bookmarks INTEGER DEFAULT 0,
    quotes INTEGER DEFAULT 0
);
"""

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS format_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    format_bucket TEXT NOT NULL,
    period_days INTEGER NOT NULL,
    avg_total_lift REAL,
    sample_count INTEGER,
    unique_authors INTEGER,
    computed_at TEXT DEFAULT (datetime('now'))
);
"""


def _make_pulse_db(tmp_path: Path) -> Path:
    path = tmp_path / "pulse.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_PULSE_SCHEMA)
    conn.commit()
    conn.close()
    return path


def _make_meta_db(tmp_path: Path) -> Path:
    path = tmp_path / "meta.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_META_SCHEMA)
    conn.commit()
    conn.close()
    return path


def _recent_iso(days_ago: int = 1) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def _insert_post(conn: sqlite3.Connection, post_id: str, handle: str,
                 ct: str = "text", days_ago: int = 1) -> None:
    conn.execute(
        """INSERT INTO posts (id, account_handle, text, posted_at, sable_content_type)
           VALUES (?, ?, ?, ?, ?)""",
        (post_id, handle, f"text of {post_id}", _recent_iso(days_ago), ct),
    )


def _open_pulse(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _open_meta(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Vault note helper
# ---------------------------------------------------------------------------

def _write_vault_note(vault_root: Path, filename: str, frontmatter: dict) -> Path:
    """Write a minimal vault note into content/ subdirectory."""
    import yaml
    content_dir = vault_root / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    path = content_dir / filename
    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    path.write_text(f"---\n{fm_yaml}---\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Slice A — _get_posting_history
# ---------------------------------------------------------------------------

def test_posting_history_format_distribution(tmp_path: Path) -> None:
    db_path = _make_pulse_db(tmp_path)
    conn = _open_pulse(db_path)

    for i in range(3):
        _insert_post(conn, f"clip-{i}", "@alice", "clip", days_ago=i + 1)
    for i in range(3):
        _insert_post(conn, f"text-{i}", "@alice", "text", days_ago=i + 1)
    conn.commit()

    result = _get_posting_history("@alice", 30, conn)
    conn.close()

    assert result["format_counts"]["short_clip"] == 3
    assert result["format_counts"]["standalone_text"] == 3
    assert result["total_posts"] == 6


def test_posting_history_empty_db(tmp_path: Path) -> None:
    db_path = _make_pulse_db(tmp_path)
    conn = _open_pulse(db_path)

    result = _get_posting_history("@alice", 30, conn)
    conn.close()

    assert result["total_posts"] == 0
    assert result["format_counts"] == {}


# ---------------------------------------------------------------------------
# Slice A — _get_vault_inventory
# ---------------------------------------------------------------------------

def test_vault_inventory_excludes_posted(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    _write_vault_note(vault_root, "note1.md", {
        "id": "note-001",
        "type": "clip",
        "account": "@alice",
        "topics": ["defi"],
        "posted_by": [{"account": "@alice", "tweet_id": "123", "posted_at": "2026-01-01", "org": "testorg"}],
    })

    result = _get_vault_inventory("@alice", "testorg", vault_root)
    assert result == []


def test_vault_inventory_includes_suggested_for(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    _write_vault_note(vault_root, "note2.md", {
        "id": "note-002",
        "type": "meme",
        "account": "@bob",
        "suggested_for": ["@alice"],
        "topics": ["nft"],
        "posted_by": [],
    })

    result = _get_vault_inventory("@alice", "testorg", vault_root)
    assert len(result) == 1
    assert result[0]["note_id"] == "note-002"
    assert result[0]["type"] == "meme"


def test_vault_inventory_includes_account_match(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    _write_vault_note(vault_root, "note3.md", {
        "id": "note-003",
        "type": "explainer",
        "account": "@alice",
        "topics": ["l2"],
        "posted_by": [],
    })

    result = _get_vault_inventory("@alice", "testorg", vault_root)
    assert len(result) == 1
    assert result[0]["note_id"] == "note-003"


def test_vault_inventory_empty_directory(tmp_path: Path) -> None:
    result = _get_vault_inventory("@alice", "testorg", None)
    assert result == []


def test_vault_inventory_nonexistent_vault(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_vault"
    result = _get_vault_inventory("@alice", "testorg", missing)
    assert result == []


# ---------------------------------------------------------------------------
# Slice A — _get_format_trends
# ---------------------------------------------------------------------------

def test_format_trends_loaded(tmp_path: Path) -> None:
    db_path = _make_meta_db(tmp_path)
    conn = _open_meta(db_path)

    conn.execute(
        """INSERT INTO format_baselines (org, format_bucket, period_days, avg_total_lift, computed_at)
           VALUES (?, ?, 7, ?, '2026-03-01T00:00:00')""",
        ("testorg", "short_clip", 2.1),
    )
    conn.execute(
        """INSERT INTO format_baselines (org, format_bucket, period_days, avg_total_lift, computed_at)
           VALUES (?, ?, 7, ?, '2026-03-01T00:00:00')""",
        ("testorg", "standalone_text", 1.4),
    )
    conn.commit()

    result = _get_format_trends("testorg", conn)
    conn.close()

    assert abs(result["short_clip"] - 2.1) < 0.01
    assert abs(result["standalone_text"] - 1.4) < 0.01


def test_format_trends_empty(tmp_path: Path) -> None:
    db_path = _make_meta_db(tmp_path)
    conn = _open_meta(db_path)
    result = _get_format_trends("testorg", conn)
    conn.close()
    assert result == {}


# ---------------------------------------------------------------------------
# Slice B — build_calendar (mocked Claude)
# ---------------------------------------------------------------------------

def test_build_calendar_mocked_claude(tmp_path: Path, monkeypatch) -> None:
    from sable.calendar.planner import build_calendar

    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    fake_response = {
        "days": [
            {
                "date": "2026-03-25",
                "day_name": "Mon Mar 25",
                "slots": [
                    {
                        "format_bucket": "standalone_text",
                        "topic_suggestion": "perp funding rate",
                        "action": "create",
                        "vault_note_id": None,
                        "rationale": "text surging",
                    }
                ],
            },
            {
                "date": "2026-03-26",
                "day_name": "Tue Mar 26",
                "slots": [
                    {
                        "format_bucket": "short_clip",
                        "topic_suggestion": "L2 scaling",
                        "action": "post_ready",
                        "vault_note_id": "clip-001",
                        "rationale": "vault item ready",
                    }
                ],
            },
        ]
    }

    monkeypatch.setattr(
        "sable.calendar.planner.call_claude_json",
        lambda *a, **kw: fake_response,
    )

    plan = build_calendar(
        handle="@alice",
        org="testorg",
        days=2,
        formats_target=2,
        pulse_db_path=pulse_db,
        meta_db_path=meta_db,
        vault_root=None,
    )

    assert len(plan.days) == 2
    assert "standalone_text" in plan.formats_covered
    assert "short_clip" in plan.formats_covered
    assert plan.vault_items_scheduled == 1
    assert plan.creation_tasks == 1


def test_build_calendar_no_vault(tmp_path: Path, monkeypatch) -> None:
    from sable.calendar.planner import build_calendar

    pulse_db = _make_pulse_db(tmp_path)

    fake_response = {
        "days": [
            {
                "date": "2026-03-25",
                "day_name": "Mon Mar 25",
                "slots": [
                    {
                        "format_bucket": "standalone_text",
                        "topic_suggestion": "crypto basics",
                        "action": "create",
                        "vault_note_id": None,
                        "rationale": "good fit",
                    }
                ],
            }
        ]
    }

    monkeypatch.setattr(
        "sable.calendar.planner.call_claude_json",
        lambda *a, **kw: fake_response,
    )

    plan = build_calendar(
        handle="@alice",
        org="testorg",
        days=1,
        formats_target=1,
        pulse_db_path=pulse_db,
        meta_db_path=None,
        vault_root=None,
    )

    assert len(plan.days) == 1
    assert plan.vault_items_scheduled == 0


# ---------------------------------------------------------------------------
# Slice B — render_calendar
# ---------------------------------------------------------------------------

def test_render_calendar_output() -> None:
    plan = CalendarPlan(
        handle="@alice",
        org="testorg",
        days=[
            CalendarDay(
                date="2026-03-25",
                day_name="Mon Mar 25",
                slots=[
                    CalendarSlot(
                        format_bucket="standalone_text",
                        topic_suggestion="perp funding rate",
                        action="create",
                        vault_note_id=None,
                        rationale="text surging at 2.3x",
                    )
                ],
            ),
            CalendarDay(
                date="2026-03-26",
                day_name="Tue Mar 26",
                slots=[
                    CalendarSlot(
                        format_bucket="short_clip",
                        topic_suggestion="L2 scaling explained",
                        action="post_ready",
                        vault_note_id="clip-001",
                        rationale="clip in vault",
                    )
                ],
            ),
        ],
        formats_covered=["short_clip", "standalone_text"],
        vault_items_scheduled=1,
        creation_tasks=1,
        generated_at="2026-03-25T12:00:00+00:00",
    )

    output = render_calendar(plan)

    assert "@alice" in output
    assert "Mon" in output
    assert "POST READY" in output
    assert "clip-001" in output
    assert len(output) > 0
