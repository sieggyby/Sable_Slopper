"""Claude API recommendations based on structured performance data."""
from __future__ import annotations

import json
from typing import Optional

from sable.roster.models import Account
from sable.shared.api import build_account_context, call_claude_json
from sable.pulse.db import get_posts_for_account, get_latest_snapshot, save_recommendation
from sable.pulse.scorer import score_post, rank_posts


def generate_recommendations(
    account: Account,
    followers: int = 1000,
    top_n: int = 10,
) -> dict:
    """
    Generate structured content recommendations for an account
    based on its performance data.
    """
    account_context = build_account_context(account)
    posts = get_posts_for_account(account.handle, limit=100)

    scored = []
    for post in posts:
        snap = get_latest_snapshot(post["id"])
        if not snap:
            continue
        scores = score_post(snap, followers=followers)
        scores["text"] = post.get("text", "")[:200]
        scores["content_type"] = post.get("sable_content_type", "unknown")
        scored.append(scores)

    if not scored:
        return {
            "recommendations": [],
            "summary": "No performance data available. Track posts first with: sable pulse track",
        }

    ranked = rank_posts(scored)
    top = ranked[:top_n]
    bottom = ranked[-top_n:] if len(ranked) > top_n else []

    top_summary = "\n".join(
        f"  - [{p['content_type']}] ER={p['engagement_rate']:.2f}% | {p['text'][:80]}"
        for p in top
    )
    bottom_summary = "\n".join(
        f"  - [{p['content_type']}] ER={p['engagement_rate']:.2f}% | {p['text'][:80]}"
        for p in bottom
    )

    prompt = f"""You are a content strategist analyzing crypto Twitter performance data.

{account_context}

## Top Performing Content (last period):
{top_summary or "(none)"}

## Lowest Performing Content:
{bottom_summary or "(none)"}

## Task
Analyze the patterns and generate actionable content recommendations.

Return JSON:
{{
  "summary": "<2-3 sentence performance summary>",
  "recommendations": [
    {{
      "priority": "high|medium|low",
      "type": "format|topic|timing|voice|template",
      "action": "<specific actionable recommendation>",
      "rationale": "<why, based on the data>"
    }},
    ...
  ],
  "content_ideas": [
    "<specific post idea based on what's working>",
    ...
  ],
  "avoid": ["<what to stop doing>", ...]
}}
"""

    raw = call_claude_json(prompt, max_tokens=2048)
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        result = {"summary": raw[:500], "recommendations": [], "content_ideas": [], "avoid": []}

    # Save to DB
    save_recommendation(account.handle, json.dumps(result))
    return result
