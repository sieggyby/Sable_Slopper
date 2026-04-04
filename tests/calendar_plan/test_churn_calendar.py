"""Tests for churn integration in calendar planner."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from sable.calendar.planner import (
    CalendarSlot, CalendarDay, CalendarPlan,
    _build_churn_prompt_section, _enforce_churn_cap, _parse_calendar_response,
    CHURN_SLOT_CAP,
)


# ---------------------------------------------------------------------------
# _build_churn_prompt_section tests
# ---------------------------------------------------------------------------

def test_churn_prompt_empty_input():
    """No churn playbook → empty string."""
    assert _build_churn_prompt_section(None, False) == ""
    assert _build_churn_prompt_section([], False) == ""


def test_churn_prompt_with_members():
    """Churn members → rendered into prompt section."""
    members = [
        {"handle": "@alice", "decay_score": 0.8, "topics": ["DeFi"], "role": "mod"},
        {"handle": "@bob", "decay_score": 0.5, "topics": ["NFTs", "gaming"], "role": "member"},
    ]
    result = _build_churn_prompt_section(members, False)
    assert "Re-engagement Targets" in result
    assert "@alice" in result
    assert "@bob" in result
    assert "30%" in result


def test_churn_prompt_prioritize_removes_cap():
    """--prioritize-churn → no percentage cap mentioned."""
    members = [{"handle": "@alice", "topics": []}]
    result = _build_churn_prompt_section(members, True)
    assert "Re-engagement Targets" in result
    assert "as many slots as possible" in result
    assert "30%" not in result


def test_churn_prompt_deduplicates():
    """Duplicate handles → deduplicated."""
    members = [
        {"handle": "@alice", "topics": []},
        {"handle": "@alice", "topics": ["DeFi"]},
    ]
    result = _build_churn_prompt_section(members, False)
    assert result.count("@alice") == 1


# ---------------------------------------------------------------------------
# _enforce_churn_cap tests
# ---------------------------------------------------------------------------

def _make_plan(slot_data: list[tuple[str, list[str]]]) -> CalendarPlan:
    """Build a plan with one day containing slots as (format, churn_targets)."""
    slots = [
        CalendarSlot(
            format_bucket=fmt, topic_suggestion="t", action="create",
            vault_note_id=None, rationale="r", churn_targets=targets,
        )
        for fmt, targets in slot_data
    ]
    day = CalendarDay(date="2026-04-01", day_name="Wed Apr 01", slots=slots)
    return CalendarPlan(
        handle="@test", org="testorg", days=[day],
        formats_covered=["text"], vault_items_scheduled=0,
        creation_tasks=len(slots), generated_at="now",
    )


def test_enforce_cap_strips_excess():
    """10 slots, all with churn → only first 3 keep targets (30% of 10 = 3)."""
    data = [(f"fmt{i}", ["@alice"]) for i in range(10)]
    plan = _make_plan(data)
    _enforce_churn_cap(plan)

    all_slots = plan.days[0].slots
    churn_count = sum(1 for s in all_slots if s.churn_targets)
    assert churn_count == 3  # int(10 * 0.30)


def test_enforce_cap_under_limit():
    """2 of 10 slots have churn → both kept (under 30%)."""
    data = [(f"fmt{i}", ["@alice"] if i < 2 else []) for i in range(10)]
    plan = _make_plan(data)
    _enforce_churn_cap(plan)

    all_slots = plan.days[0].slots
    churn_count = sum(1 for s in all_slots if s.churn_targets)
    assert churn_count == 2


def test_enforce_cap_empty_plan():
    """Empty plan → no crash."""
    plan = CalendarPlan(
        handle="@test", org="testorg", days=[],
        formats_covered=[], vault_items_scheduled=0,
        creation_tasks=0, generated_at="now",
    )
    _enforce_churn_cap(plan)  # no crash


def test_enforce_cap_multi_day():
    """Churn cap counts slots across all days."""
    days = [
        CalendarDay(
            date=f"2026-04-0{d+1}", day_name=f"Day {d+1}",
            slots=[
                CalendarSlot(
                    format_bucket=f"fmt{d}_{s}", topic_suggestion="t",
                    action="create", vault_note_id=None, rationale="r",
                    churn_targets=["@alice"],
                )
                for s in range(2)
            ],
        )
        for d in range(5)
    ]
    plan = CalendarPlan(
        handle="@test", org="testorg", days=days,
        formats_covered=["text"], vault_items_scheduled=0,
        creation_tasks=10, generated_at="now",
    )
    _enforce_churn_cap(plan)
    churn_count = sum(1 for d in plan.days for s in d.slots if s.churn_targets)
    assert churn_count == 3  # int(10 * 0.30) = 3


# ---------------------------------------------------------------------------
# _parse_calendar_response with churn_targets
# ---------------------------------------------------------------------------

def test_parse_preserves_churn_targets():
    """Parsed response preserves churn_targets on slots."""
    raw = json.dumps({
        "days": [{
            "date": "2026-04-01",
            "day_name": "Wed Apr 01",
            "slots": [{
                "format_bucket": "text",
                "topic_suggestion": "governance update",
                "action": "create",
                "vault_note_id": None,
                "rationale": "re-engage governance voices",
                "churn_targets": ["@alice", "@bob"],
            }],
        }],
    })
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    plan = _parse_calendar_response(raw, "@test", "testorg", 1, now)
    assert plan.days[0].slots[0].churn_targets == ["@alice", "@bob"]


def test_parse_missing_churn_defaults_empty():
    """Slot without churn_targets → defaults to empty list."""
    raw = json.dumps({
        "days": [{
            "date": "2026-04-01",
            "day_name": "Wed Apr 01",
            "slots": [{
                "format_bucket": "text",
                "topic_suggestion": "t",
                "action": "create",
                "vault_note_id": None,
                "rationale": "r",
            }],
        }],
    })
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    plan = _parse_calendar_response(raw, "@test", "testorg", 1, now)
    assert plan.days[0].slots[0].churn_targets == []


def test_no_churn_input_calendar_unchanged():
    """No churn playbook → no churn_targets on any slot."""
    raw = json.dumps({
        "days": [{
            "date": "2026-04-01",
            "day_name": "Wed Apr 01",
            "slots": [{
                "format_bucket": "text",
                "topic_suggestion": "t",
                "action": "create",
                "vault_note_id": None,
                "rationale": "r",
            }],
        }],
    })
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    plan = _parse_calendar_response(raw, "@test", "testorg", 1, now)
    for day in plan.days:
        for slot in day.slots:
            assert slot.churn_targets == []
