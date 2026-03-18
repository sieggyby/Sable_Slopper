"""Claude API clip selection — injects full account context."""
from __future__ import annotations

import json
from typing import Optional

from sable.roster.models import Account
from sable.shared.api import build_account_context, call_claude_json


def select_clips(
    transcript: dict,
    account: Account,
    num_clips: int = 3,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    dry_run: bool = False,
) -> list[dict]:
    """
    Use Claude to identify the best clip segments from a transcript.

    Returns list of dicts: [{start, end, reason, hook, caption_hint}]
    """
    account_context = build_account_context(
        account, profile_files=["tone", "interests", "context"]
    )

    segments_text = "\n".join(
        f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}"
        for s in transcript.get("segments", [])
    )
    if not segments_text:
        segments_text = transcript.get("text", "(no transcript)")

    prompt = f"""You are a social media content strategist for crypto Twitter.

{account_context}

## Video Transcript (with timestamps):
{segments_text}

## Task
Select the {num_clips} best clips for vertical short-form video (TikTok/Reels/Shorts).

Requirements:
- Each clip must be {min_duration}–{max_duration} seconds long
- Choose clips with strong hooks, quotable moments, or viral potential
- Match the account's voice and topics above
- Prioritize moments that feel native to crypto Twitter

Return JSON array only. Each element:
{{
  "start": <float seconds>,
  "end": <float seconds>,
  "reason": "<why this clip works for this account>",
  "hook": "<the first line/hook for the caption>",
  "caption_hint": "<suggested tweet text>"
}}
"""

    if dry_run:
        return [{
            "start": 0.0,
            "end": min(30.0, max_duration),
            "reason": "DRY RUN — first 30s",
            "hook": "DRY RUN",
            "caption_hint": f"[dry run clip for {account.handle}]",
        }]

    raw = call_claude_json(prompt, max_tokens=1024)

    try:
        # Strip any accidental markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        clips = json.loads(raw)
        if isinstance(clips, dict) and "clips" in clips:
            clips = clips["clips"]
        return clips[:num_clips]
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude returned invalid JSON: {e}\nRaw: {raw[:500]}")
