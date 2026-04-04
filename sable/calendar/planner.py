"""Calendar planner: generate a posting schedule for an account."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sable.shared.api import call_claude_json


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CalendarSlot:
    format_bucket: str
    topic_suggestion: str
    action: str               # "post_ready" | "create"
    vault_note_id: Optional[str]
    rationale: str
    churn_targets: list[str] = field(default_factory=list)


@dataclass
class CalendarDay:
    date: str                 # YYYY-MM-DD
    day_name: str             # "Mon Mar 25"
    slots: list[CalendarSlot]


@dataclass
class CalendarPlan:
    handle: str
    org: str
    days: list[CalendarDay]
    formats_covered: list[str]
    vault_items_scheduled: int
    creation_tasks: int
    generated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_posting_history(handle: str, days: int, conn: sqlite3.Connection) -> dict:
    """Return posting history for the last N days from pulse.db."""
    from sable.pulse.attribution import _content_type_to_format_bucket

    h = handle if handle.startswith("@") else f"@{handle}"
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = conn.execute(
        """SELECT p.id, p.sable_content_type, p.sable_content_path, p.posted_at
           FROM posts p
           WHERE p.account_handle = ? AND p.posted_at >= ?
           ORDER BY p.posted_at DESC""",
        (h, cutoff),
    ).fetchall()

    format_counts: dict[str, int] = {}
    last_posted_at: dict[str, str] = {}

    for row in rows:
        bucket = _content_type_to_format_bucket(
            row[1] if isinstance(row, tuple) else row["sable_content_type"],
            row[2] if isinstance(row, tuple) else row["sable_content_path"],
        )
        if bucket is None:
            continue
        format_counts[bucket] = format_counts.get(bucket, 0) + 1
        posted_at = row[3] if isinstance(row, tuple) else row["posted_at"]
        if bucket not in last_posted_at:
            last_posted_at[bucket] = posted_at

    total_posts = sum(format_counts.values())
    posts_per_day = total_posts / days if days else 0.0

    now = datetime.now(timezone.utc)
    days_since_last: dict[str, int] = {}
    for bucket, ts in last_posted_at.items():
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days_since_last[bucket] = (now - dt).days
        except Exception:
            pass

    return {
        "format_counts": format_counts,
        "posts_per_day": posts_per_day,
        "days_since_last": days_since_last,
        "total_posts": total_posts,
    }


def _get_vault_inventory(handle: str, org: str, vault_root: Optional[Path]) -> list[dict]:
    """Return unposted vault notes assigned to this account."""
    if vault_root is None or not vault_root.exists():
        return []

    from sable.vault.notes import load_all_notes

    h = handle if handle.startswith("@") else f"@{handle}"
    all_notes = load_all_notes(vault_root)

    result = []
    for n in all_notes:
        note_type = n.get("type")
        if note_type not in ("clip", "meme", "faceswap", "explainer"):
            continue

        # Exclude if already posted by this handle
        posted_by = n.get("posted_by") or []
        if any(e.get("account") == h for e in posted_by):
            continue

        # Include if account matches or handle is in suggested_for
        account_match = n.get("account") == h
        suggested_for = n.get("suggested_for") or []
        if not account_match and h not in suggested_for:
            continue

        note_id = n.get("id") or Path(n.get("_note_path", "")).stem
        result.append({
            "note_id": note_id,
            "path": n.get("_note_path"),
            "type": note_type,
            "topics": n.get("topics") or [],
            "assembled_at": n.get("assembled_at"),
            "output": n.get("output"),
        })

    return result


def _get_format_trends(org: str, conn: sqlite3.Connection) -> dict[str, float]:
    """Return latest avg_total_lift per format_bucket (period_days=7) from meta.db."""
    try:
        rows = conn.execute(
            """SELECT f.format_bucket, f.avg_total_lift
               FROM format_baselines f
               WHERE f.org = ? AND f.period_days = 7
                 AND f.computed_at = (
                     SELECT MAX(f2.computed_at) FROM format_baselines f2
                     WHERE f2.org = f.org AND f2.format_bucket = f.format_bucket
                       AND f2.period_days = 7
                 )""",
            (org,),
        ).fetchall()
    except Exception:
        return {}

    result: dict[str, float] = {}
    for row in rows:
        bucket = row[0] if isinstance(row, tuple) else row["format_bucket"]
        lift = row[1] if isinstance(row, tuple) else row["avg_total_lift"]
        if bucket and lift is not None:
            result[bucket] = lift
    return result


# ---------------------------------------------------------------------------
# Build + Render
# ---------------------------------------------------------------------------

CHURN_SLOT_CAP = 0.30  # max fraction of slots for churn re-engagement


def _build_churn_prompt_section(
    churn_playbook: list[dict] | None,
    prioritize_churn: bool,
) -> str:
    """Build the churn re-engagement prompt section."""
    if not churn_playbook:
        return ""

    # Deduplicate by handle
    seen: set[str] = set()
    unique: list[dict] = []
    for member in churn_playbook:
        h = member.get("handle", "")
        if h and h not in seen:
            seen.add(h)
            unique.append(member)

    lines = ["\n## Re-engagement Targets"]
    lines.append("The following at-risk members should be targeted for re-engagement.")
    if not prioritize_churn:
        lines.append(
            f"Annotate up to {int(CHURN_SLOT_CAP * 100)}% of slots with churn_targets "
            "containing the handles of members this content could re-engage."
        )
    else:
        lines.append(
            "Annotate as many slots as possible with churn_targets "
            "containing the handles of members this content could re-engage."
        )

    for m in unique[:20]:  # cap context size
        topics = ", ".join(m.get("topics", [])) if m.get("topics") else "none"
        lines.append(
            f"- {m.get('handle', '?')}: "
            f"decay={m.get('decay_score', '?')}, "
            f"topics=[{topics}], "
            f"role={m.get('role', 'member')}"
        )

    return "\n".join(lines) + "\n"


def build_calendar(
    handle: str,
    org: str,
    days: int,
    formats_target: int,
    pulse_db_path: Path,
    meta_db_path: Optional[Path],
    vault_root: Optional[Path],
    churn_playbook: Optional[list[dict]] = None,
    prioritize_churn: bool = False,
) -> CalendarPlan:
    """Assemble inputs and call Claude to produce a CalendarPlan."""
    h = handle if handle.startswith("@") else f"@{handle}"

    # --- deterministic inputs ---
    pulse_conn = sqlite3.connect(str(pulse_db_path))
    pulse_conn.row_factory = sqlite3.Row
    try:
        history = _get_posting_history(h, days, pulse_conn)
    finally:
        pulse_conn.close()

    trends: dict[str, float] = {}
    if meta_db_path and meta_db_path.exists():
        meta_conn = sqlite3.connect(str(meta_db_path))
        meta_conn.row_factory = sqlite3.Row
        try:
            trends = _get_format_trends(org, meta_conn)
        finally:
            meta_conn.close()

    inventory = _get_vault_inventory(h, org, vault_root)

    # --- prompt ---
    now = datetime.now(timezone.utc)
    horizon_start = now.strftime("%Y-%m-%d")
    horizon_end = (now + timedelta(days=days - 1)).strftime("%Y-%m-%d")

    inventory_lines = []
    for item in inventory:
        topics_str = ", ".join(item["topics"]) if item["topics"] else "none"
        inventory_lines.append(
            f"  - id={item['note_id']} type={item['type']} topics=[{topics_str}]"
            f" assembled_at={item['assembled_at']}"
        )
    inventory_text = "\n".join(inventory_lines) if inventory_lines else "  (empty)"

    trend_lines = [f"  {b}: {v:.2f}x" for b, v in sorted(trends.items())]
    trend_text = "\n".join(trend_lines) if trend_lines else "  (no data)"

    prompt = f"""Generate a {days}-day content posting calendar for {h} (org: {org}).
Planning window: {horizon_start} to {horizon_end}
Target format diversity: {formats_target} unique format buckets across the week.

Posting history (last {days} days):
  format counts: {json.dumps(history['format_counts'])}
  posts per day: {history['posts_per_day']:.2f}
  days since last post by format: {json.dumps(history['days_since_last'])}

Vault inventory (ready, unposted):
{inventory_text}

Format trends (avg_total_lift, period=7d):
{trend_text}

Constraints:
- Do not schedule a declining format (lift < 0.8) more than once per week.
- Prioritise formats with lift > 1.5.
- Use "post_ready" action + vault_note_id when scheduling a vault item; otherwise "create".
- Return exactly {days} days starting from {horizon_start}.
- Each day should have 1–2 slots.
{_build_churn_prompt_section(churn_playbook, prioritize_churn)}
Return JSON with this exact structure:
{{
  "days": [
    {{
      "date": "YYYY-MM-DD",
      "day_name": "Mon Mar 25",
      "slots": [
        {{
          "format_bucket": "standalone_text",
          "topic_suggestion": "...",
          "action": "create",
          "vault_note_id": null,
          "rationale": "...",
          "churn_targets": []
        }}
      ]
    }}
  ]
}}"""

    system = (
        "You are a crypto-Twitter content strategist. "
        "Return only valid JSON — no markdown fences, no commentary."
    )

    raw = call_claude_json(prompt, system, org_id=org, call_type="calendar", max_tokens=2048)

    plan = _parse_calendar_response(raw, h, org, days, now)

    # Enforce churn slot cap
    if churn_playbook and not prioritize_churn:
        _enforce_churn_cap(plan)

    return plan


def _enforce_churn_cap(plan: CalendarPlan) -> None:
    """Strip churn_targets from excess slots to respect CHURN_SLOT_CAP."""
    all_slots = [s for d in plan.days for s in d.slots]
    total = len(all_slots)
    if total == 0:
        return

    max_churn = max(1, int(total * CHURN_SLOT_CAP))
    churn_count = 0
    for slot in all_slots:
        if slot.churn_targets:
            churn_count += 1
            if churn_count > max_churn:
                slot.churn_targets = []


def _parse_calendar_response(
    raw: dict | str | None,
    handle: str,
    org: str,
    days: int,
    now: datetime,
) -> CalendarPlan:
    """Parse Claude JSON response into a CalendarPlan; fall back on error."""
    generated_at = now.isoformat()

    try:
        data = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        raw_days = data.get("days", [])
        if not isinstance(raw_days, list):
            raise ValueError("days not a list")

        calendar_days: list[CalendarDay] = []
        formats_covered: set[str] = set()
        vault_items = 0
        creation_tasks = 0

        for d in raw_days:
            slots: list[CalendarSlot] = []
            for s in d.get("slots", []):
                slot = CalendarSlot(
                    format_bucket=s.get("format_bucket", "unknown"),
                    topic_suggestion=s.get("topic_suggestion", ""),
                    action=s.get("action", "create"),
                    vault_note_id=s.get("vault_note_id"),
                    rationale=s.get("rationale", ""),
                    churn_targets=s.get("churn_targets", []),
                )
                slots.append(slot)
                formats_covered.add(slot.format_bucket)
                if slot.action == "post_ready":
                    vault_items += 1
                else:
                    creation_tasks += 1

            calendar_days.append(CalendarDay(
                date=d.get("date", ""),
                day_name=d.get("day_name", ""),
                slots=slots,
            ))

        return CalendarPlan(
            handle=handle,
            org=org,
            days=calendar_days,
            formats_covered=sorted(formats_covered),
            vault_items_scheduled=vault_items,
            creation_tasks=creation_tasks,
            generated_at=generated_at,
        )

    except Exception:
        # Minimal fallback
        fallback_day = CalendarDay(
            date=now.strftime("%Y-%m-%d"),
            day_name=now.strftime("%a %b %d").lstrip("0"),
            slots=[CalendarSlot(
                format_bucket="standalone_text",
                topic_suggestion="(calendar generation failed — retry)",
                action="create",
                vault_note_id=None,
                rationale="Fallback slot: Claude response could not be parsed.",
            )],
        )
        return CalendarPlan(
            handle=handle,
            org=org,
            days=[fallback_day],
            formats_covered=["standalone_text"],
            vault_items_scheduled=0,
            creation_tasks=1,
            generated_at=generated_at,
        )


def render_calendar(plan: CalendarPlan) -> str:
    """Render a CalendarPlan as a human-readable markdown string."""
    lines: list[str] = []

    if plan.days:
        first = plan.days[0]
        last = plan.days[-1]
        window = f"{first.day_name} → {last.day_name}"
    else:
        window = "(empty)"

    lines.append(f"# {plan.handle} — {len(plan.days)}-Day Content Calendar")
    lines.append(window)
    lines.append("")

    for day in plan.days:
        lines.append(f"## {day.day_name}")
        for i, slot in enumerate(day.slots, 1):
            num = "①②③④⑤⑥⑦⑧⑨"[i - 1] if i <= 9 else str(i)
            action_label = f"POST READY → {slot.vault_note_id}" if slot.action == "post_ready" else "CREATE"
            lines.append(f"  {num} {slot.format_bucket} · \"{slot.topic_suggestion}\" · {action_label}")
            if slot.rationale:
                lines.append(f"     Why: {slot.rationale}")
        lines.append("")

    lines.append("---")
    total_formats = len(plan.formats_covered)
    total_days = len(plan.days)
    lines.append(
        f"Summary: {total_formats} format{'s' if total_formats != 1 else ''} across "
        f"{total_days} day{'s' if total_days != 1 else ''} · "
        f"{plan.vault_items_scheduled} vault piece{'s' if plan.vault_items_scheduled != 1 else ''} scheduled · "
        f"{plan.creation_tasks} new creation task{'s' if plan.creation_tasks != 1 else ''}"
    )
    lines.append(f"Generated: {plan.generated_at}")

    return "\n".join(lines)
