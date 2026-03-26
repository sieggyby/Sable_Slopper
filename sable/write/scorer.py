"""Hook pattern extraction and draft scoring for `sable score`."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sable.platform.errors import SableError
from sable.pulse.meta.db import (
    get_high_lift_tweets,
    get_hook_patterns_cache,
    get_latest_successful_scan_at,
    upsert_hook_patterns,
)
from sable.roster.manager import require_account
from sable.shared.api import call_claude_json
from sable.shared.paths import profile_dir

logger = logging.getLogger(__name__)


@dataclass
class HookPattern:
    name: str
    description: str
    example: str


@dataclass
class HookScore:
    grade: str
    score: float
    matched_pattern: str | None
    voice_fit: int
    flags: list[str] = field(default_factory=list)
    suggested_rewrite: str | None = None


# ---------------------------------------------------------------------------
# Cache staleness
# ---------------------------------------------------------------------------

def _is_cache_stale(cache_row: dict, org: str) -> bool:
    """Return True if cache is >24h old OR a newer scan exists since it was generated."""
    generated_at_str: str = cache_row["generated_at"]
    try:
        generated_at = datetime.fromisoformat(generated_at_str)
    except (ValueError, TypeError):
        return True

    # Ensure timezone-aware for comparison
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if now - generated_at > timedelta(hours=24):
        return True

    latest_scan = get_latest_successful_scan_at(org)
    if latest_scan is not None:
        try:
            scan_dt = datetime.fromisoformat(latest_scan)
            if scan_dt.tzinfo is None:
                scan_dt = scan_dt.replace(tzinfo=timezone.utc)
            if scan_dt > generated_at:
                return True
        except (ValueError, TypeError):
            pass

    return False


# ---------------------------------------------------------------------------
# Pattern retrieval
# ---------------------------------------------------------------------------

def get_hook_patterns(org: str, format_bucket: str) -> list[HookPattern]:
    """Return hook patterns for org+format, using cache when fresh."""
    cache_row = get_hook_patterns_cache(org, format_bucket)
    if cache_row and not _is_cache_stale(cache_row, org):
        try:
            raw_patterns = json.loads(cache_row["patterns_json"])
            return [HookPattern(**p) for p in raw_patterns]
        except (KeyError, TypeError, json.JSONDecodeError):
            logger.warning("Failed to parse cached hook patterns; regenerating.")

    tweets = get_high_lift_tweets(org, format_bucket)
    if len(tweets) < 5:
        raise SableError(
            "NO_SCAN_DATA",
            f"Not enough high-lift {format_bucket} tweets for {org}. "
            "Run `sable pulse meta scan` first.",
        )

    tweet_texts = "\n".join(
        f"- {t['text'][:280]}" for t in tweets if t.get("text")
    )
    prompt = (
        f"Below are high-performing {format_bucket} tweets from the watchlist for org '{org}':\n\n"
        f"{tweet_texts}\n\n"
        "Identify 3–6 recurring hook patterns that make these tweets perform well.\n"
        'Return JSON: {"patterns": [{"name": "...", "description": "...", "example": "..."}]}'
    )
    system = (
        "You are an expert social media analyst. "
        "Extract structural hook patterns from high-performing tweets. "
        "Be concise and specific."
    )

    raw = call_claude_json(prompt, system=system, call_type="score_patterns")
    parsed = json.loads(raw)
    patterns_list = parsed["patterns"]
    patterns_json = json.dumps(patterns_list)
    upsert_hook_patterns(org, format_bucket, patterns_json)
    return [HookPattern(**p) for p in patterns_list]


# ---------------------------------------------------------------------------
# Draft scoring
# ---------------------------------------------------------------------------

def score_draft(
    handle: str,
    draft_text: str,
    format_bucket: str,
    org: str | None,
) -> HookScore:
    """Score a draft tweet's hook against recent high-performing patterns."""
    acc = require_account(handle)
    resolved_org: str = org or acc.org or ""

    patterns = get_hook_patterns(resolved_org, format_bucket)

    tone_excerpt = ""
    tone_path = profile_dir(handle) / "tone.md"
    try:
        tone_excerpt = tone_path.read_text(encoding="utf-8")[:200]
    except (OSError, FileNotFoundError):
        pass

    numbered_patterns = "\n".join(
        f"{i}. {p.name} — {p.description} — e.g. \"{p.example}\""
        for i, p in enumerate(patterns, 1)
    )

    prompt = (
        f"Account voice profile:\n{tone_excerpt}\n\n"
        f"High-performing hook patterns in {format_bucket} right now:\n{numbered_patterns}\n\n"
        f"Draft tweet:\n{draft_text}\n\n"
        "Score this draft 1-10 on hook strength, pattern match, and voice fit.\n\n"
        'Return JSON: {"grade":"…","score":…,"matched_pattern":"…","voice_fit":…,'
        '"flags":[…],"suggested_rewrite":"…"}\n'
        'Only include "suggested_rewrite" if score < 7; omit the key otherwise.'
    )

    raw = call_claude_json(prompt, call_type="score_draft")
    data: dict = json.loads(raw)

    return HookScore(
        grade=str(data["grade"]),
        score=float(data["score"]),
        matched_pattern=data.get("matched_pattern") or None,
        voice_fit=int(data["voice_fit"]),
        flags=list(data.get("flags") or []),
        suggested_rewrite=data.get("suggested_rewrite") or None,
    )
