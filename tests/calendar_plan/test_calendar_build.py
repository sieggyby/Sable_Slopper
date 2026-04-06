"""AQ-28: Calendar module build/parse tests."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest

from sable.calendar.planner import build_calendar, CalendarPlan, CHURN_SLOT_CAP


def _make_pulse_db(tmp_path):
    """Create a minimal pulse.db with full schema."""
    path = tmp_path / "pulse.db"
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE posts (
            id TEXT PRIMARY KEY,
            account_handle TEXT NOT NULL,
            platform TEXT DEFAULT 'twitter',
            url TEXT,
            text TEXT,
            posted_at TEXT,
            sable_content_type TEXT,
            sable_content_path TEXT,
            is_thread INTEGER DEFAULT 0,
            thread_length INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE snapshots (
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
    """)
    conn.commit()
    conn.close()
    return path


VALID_CALENDAR_JSON = json.dumps({
    "days": [
        {
            "date": "2026-04-06",
            "day_name": "Mon Apr 06",
            "slots": [
                {
                    "format_bucket": "clip",
                    "topic_suggestion": "DeFi recap",
                    "action": "create",
                    "vault_note_id": None,
                    "rationale": "Clips trending at 1.8x lift",
                    "churn_targets": [],
                },
            ],
        },
        {
            "date": "2026-04-07",
            "day_name": "Tue Apr 07",
            "slots": [
                {
                    "format_bucket": "meme",
                    "topic_suggestion": "Market mood",
                    "action": "create",
                    "vault_note_id": None,
                    "rationale": "Memes have strong engagement",
                    "churn_targets": [],
                },
            ],
        },
    ],
})


def test_build_calendar_parses_claude_response(tmp_path):
    """Mock Claude → valid JSON → CalendarPlan returned."""
    pulse_path = _make_pulse_db(tmp_path)

    with patch("sable.calendar.planner.call_claude_json", return_value=VALID_CALENDAR_JSON):
        plan = build_calendar(
            handle="@test",
            org="testorg",
            days=2,
            formats_target=3,
            pulse_db_path=pulse_path,
            meta_db_path=None,
            vault_root=None,
        )

    assert isinstance(plan, CalendarPlan)
    assert len(plan.days) == 2
    assert plan.days[0].slots[0].format_bucket == "clip"
    assert plan.handle == "@test"


def test_build_calendar_empty_vault_and_pulse(tmp_path):
    """Empty pulse DB + no vault → still produces a plan."""
    pulse_path = _make_pulse_db(tmp_path)

    with patch("sable.calendar.planner.call_claude_json", return_value=VALID_CALENDAR_JSON):
        plan = build_calendar(
            handle="@test",
            org="testorg",
            days=2,
            formats_target=3,
            pulse_db_path=pulse_path,
            meta_db_path=None,
            vault_root=None,
        )

    assert isinstance(plan, CalendarPlan)


def test_build_calendar_claude_returns_invalid_json_fallback(tmp_path):
    """Claude returns non-JSON → graceful fallback plan (not crash)."""
    pulse_path = _make_pulse_db(tmp_path)

    with patch("sable.calendar.planner.call_claude_json", return_value="not json at all"):
        plan = build_calendar(
            handle="@test",
            org="testorg",
            days=2,
            formats_target=3,
            pulse_db_path=pulse_path,
            meta_db_path=None,
            vault_root=None,
        )

    assert isinstance(plan, CalendarPlan)
    assert len(plan.days) == 1  # fallback produces 1 day
    assert plan.days[0].slots[0].rationale.startswith("Fallback")


def test_churn_slot_cap_constant():
    """CHURN_SLOT_CAP is 0.30 (30%)."""
    assert CHURN_SLOT_CAP == 0.30
