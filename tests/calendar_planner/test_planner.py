"""Tests for sable.calendar.planner — T3-1: parse, render, churn cap."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sable.calendar.planner import (
    CalendarDay,
    CalendarPlan,
    CalendarSlot,
    _enforce_churn_cap,
    _parse_calendar_response,
    render_calendar,
)


# ---------------------------------------------------------------------------
# _parse_calendar_response
# ---------------------------------------------------------------------------

def test_parse_valid_response():
    """Valid Claude JSON is parsed into a CalendarPlan."""
    raw = {
        "days": [
            {
                "date": "2026-04-06",
                "day_name": "Mon Apr 06",
                "slots": [
                    {
                        "format_bucket": "clip",
                        "topic_suggestion": "defi explainer",
                        "action": "post_ready",
                        "vault_note_id": "note-1",
                        "rationale": "trending topic",
                        "churn_targets": [],
                    }
                ],
            }
        ]
    }
    now = datetime(2026, 4, 6, tzinfo=timezone.utc)
    plan = _parse_calendar_response(raw, "@alice", "testorg", 3, now)

    assert plan.handle == "@alice"
    assert plan.org == "testorg"
    assert len(plan.days) == 1
    assert plan.days[0].slots[0].format_bucket == "clip"
    assert plan.vault_items_scheduled == 1
    assert plan.creation_tasks == 0


def test_parse_malformed_response_falls_back():
    """Malformed JSON produces a fallback plan instead of crashing."""
    now = datetime(2026, 4, 6, tzinfo=timezone.utc)
    plan = _parse_calendar_response("not json at all {{{", "@bob", "testorg", 3, now)

    assert plan.handle == "@bob"
    assert len(plan.days) == 1
    assert plan.creation_tasks == 1
    assert "fallback" in plan.days[0].slots[0].rationale.lower()


def test_parse_missing_days_key():
    """Response with no 'days' key produces empty plan."""
    now = datetime(2026, 4, 6, tzinfo=timezone.utc)
    plan = _parse_calendar_response({"unrelated": True}, "@bob", "testorg", 3, now)

    assert len(plan.days) == 0


# ---------------------------------------------------------------------------
# _enforce_churn_cap
# ---------------------------------------------------------------------------

def test_enforce_churn_cap_strips_excess():
    """Churn cap strips churn_targets from excess slots."""
    slots = [
        CalendarSlot("clip", "t1", "create", None, "r", churn_targets=["@x"]),
        CalendarSlot("meme", "t2", "create", None, "r", churn_targets=["@y"]),
        CalendarSlot("text", "t3", "create", None, "r", churn_targets=["@z"]),
    ]
    day = CalendarDay(date="2026-04-06", day_name="Mon Apr 06", slots=slots)
    plan = CalendarPlan(
        handle="@alice", org="testorg", days=[day],
        formats_covered=["clip", "meme", "text"],
        vault_items_scheduled=0, creation_tasks=3,
        generated_at="2026-04-06T00:00:00",
    )

    _enforce_churn_cap(plan)

    churn_slots = [s for s in plan.days[0].slots if s.churn_targets]
    # With 3 total slots, cap = max(1, int(3 * 0.25)) = 1, so <=1 slot keeps churn
    assert len(churn_slots) <= 1


# ---------------------------------------------------------------------------
# render_calendar
# ---------------------------------------------------------------------------

def test_render_calendar_includes_handle():
    """Rendered output contains the handle and format bucket."""
    plan = CalendarPlan(
        handle="@alice", org="testorg",
        days=[
            CalendarDay(
                date="2026-04-06", day_name="Mon Apr 06",
                slots=[CalendarSlot("clip", "defi topic", "create", None, "trending")],
            )
        ],
        formats_covered=["clip"],
        vault_items_scheduled=0, creation_tasks=1,
        generated_at="2026-04-06T00:00:00",
    )
    output = render_calendar(plan)
    assert "@alice" in output
    assert "clip" in output
    assert "defi topic" in output


def test_render_empty_plan():
    """Empty plan renders without crash."""
    plan = CalendarPlan(
        handle="@bob", org="testorg", days=[],
        formats_covered=[], vault_items_scheduled=0, creation_tasks=0,
        generated_at="2026-04-06T00:00:00",
    )
    output = render_calendar(plan)
    assert "@bob" in output
    assert "(empty)" in output
