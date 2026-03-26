"""Claude analysis layer for pulse meta."""
from __future__ import annotations

import json
from typing import Optional

from sable.pulse.meta.trends import TrendResult
from sable.pulse.meta.topics import TopicSignal


_SYSTEM = """You are a crypto content strategy analyst.
You receive structured data about content performance on crypto Twitter:
format trends (how different tweet formats perform vs baselines),
and topic signals (which topics appear in high-performing content).

Your job is to synthesize this into actionable operator intelligence.
Be concise, specific, and honest about uncertainty.
Respond with valid JSON only. No markdown fences."""

_SCHEMA_NOTE = """
Respond with this exact JSON schema:
{
  "dominant_format": "<format_bucket name>",
  "dominant_format_why": "<1-2 sentences: what engagement signals this format fires and why it works>",
  "execution_notes": "<specific execution guidance: video length sweet spot, text tone, hook structure, etc.>",
  "topic_categorization": {
    "hot": ["<term>", ...],
    "rising": ["<term>", ...],
    "emerging": ["<term>", ...]
  },
  "topic_confidence": "high|medium|low",
  "meta_summary": "<3-4 sentence strategist brief: what should they post in the next hour and why>"
}

Rules:
- dominant_format must be one of the format buckets provided
- topic lists come ONLY from the provided topic signals — do not invent topics
- hot = high engagement AND high mention volume now
- rising = accelerating mentions or lift
- emerging = early signal (low volume but growing)
- meta_summary must be actionable, not descriptive
"""


def build_analysis_prompt(
    top_tweets: list[dict],
    trends: dict[str, TrendResult],
    topic_signals: list[TopicSignal],
    org: str,
) -> str:
    """Build the structured prompt for Claude."""
    sections: list[str] = []

    # Format trend data
    format_lines: list[str] = []
    for bucket, trend in sorted(
        trends.items(),
        key=lambda kv: kv[1].current_lift,
        reverse=True,
    ):
        if trend.trend_status:
            line = (
                f"- {bucket}: {trend.trend_status} ({trend.confidence}) | "
                f"lift {trend.current_lift:.2f}x | "
                f"{trend.quality.sample_count} tweets | "
                f"{trend.quality.unique_authors} authors"
            )
            if trend.momentum:
                line += f" | momentum: {trend.momentum}"
        else:
            line = (
                f"- {bucket}: no label (gates: {', '.join(trend.gate_failures[:2])}) | "
                f"raw lift {trend.current_lift:.2f}x"
            )
        format_lines.append(line)

    sections.append("## Format Trends\n" + "\n".join(format_lines))

    # Topic signals
    if topic_signals:
        topic_lines = []
        for sig in topic_signals[:20]:
            accel = f" (accel {sig.acceleration:.1f}x)" if sig.acceleration > 1.5 else ""
            topic_lines.append(
                f"- {sig.term}: {sig.mention_count} mentions, "
                f"{sig.unique_authors} authors, avg lift {sig.avg_lift:.2f}x{accel}"
            )
        sections.append("## Topic Signals (deterministic pre-pass)\n" + "\n".join(topic_lines))
    else:
        sections.append("## Topic Signals\nNo significant topics detected this scan.")

    # Top tweets
    if top_tweets:
        tweet_lines = []
        for i, t in enumerate(top_tweets[:20]):
            tweet_lines.append(
                f"{i+1}. [{t.get('format_bucket', '?')} | "
                f"lift {t.get('total_lift', 0):.1f}x | "
                f"@{t.get('author_handle', '?')}] "
                f"{t.get('text', '')[:120]}"
            )
        sections.append("## Top Performing Tweets\n" + "\n".join(tweet_lines))

    prompt = (
        f"Org: {org}\n\n"
        + "\n\n".join(sections)
        + "\n\n"
        + _SCHEMA_NOTE
    )
    return prompt


def run_analysis(
    top_tweets: list[dict],
    trends: dict[str, TrendResult],
    topic_signals: list[TopicSignal],
    org: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 1024,
) -> tuple[dict, str]:
    """Call Claude and return (parsed_json, raw_text).

    On parse failure: returns ({}, raw_text) so caller can fall back gracefully.
    """
    from sable.shared.api import call_claude_json

    prompt = build_analysis_prompt(top_tweets, trends, topic_signals, org)

    try:
        raw = call_claude_json(
            prompt,
            system=_SYSTEM,
            model=model,
            max_tokens=max_tokens,
            org_id=org,
            call_type="pulse_meta_analysis",
        )
    except Exception as e:
        return {}, f"Claude call failed: {e}"

    try:
        parsed = json.loads(raw)
        return parsed, raw
    except json.JSONDecodeError:
        return {}, raw


def fallback_analysis(trends: dict[str, TrendResult]) -> dict:
    """Produce minimal analysis dict from trends alone (no Claude)."""
    surging = [b for b, t in trends.items() if t.trend_status == "surging"]
    rising = [b for b, t in trends.items() if t.trend_status == "rising"]
    dominant = surging[0] if surging else (rising[0] if rising else None)

    return {
        "dominant_format": dominant or "unknown",
        "dominant_format_why": "Determined from quantitative trend data only (Claude unavailable).",
        "execution_notes": "Claude analysis not available.",
        "topic_categorization": {"hot": [], "rising": [], "emerging": []},
        "topic_confidence": "low",
        "meta_summary": (
            "Claude analysis unavailable — showing quantitative trends only. "
            f"Formats showing above-baseline performance: "
            f"{', '.join((surging + rising)[:3]) or 'none detected'}."
        ),
    }
