"""Stage 2: AI synthesis for Twitter strategy brief."""
from __future__ import annotations

import anthropic


OUTPUT_FORMAT_CONTRACT = """
## Output Format

Produce a markdown document with these sections (omit any section where data was absent from the input):

1. **## What's Working** — Top format + topic by lift. Only include if post performance data was provided.
2. **## What to Try** — Trending formats/topics + entity collaboration opportunities. Always present. If no trend data or entity opportunities exist, suggest 1-3 generic on-voice experiments from the account profile (do NOT label them as trend-backed).
3. **## What to Stop** — Underperforming formats. Only include if >= 10 posts were provided.
4. **## Engagement Targets** — Named entities to interact with. Only include if entities were listed in the input.
5. **## Community Content to Amplify** — SableTracking items to engage with. Only include if community content was listed in the input.

Rules:
- Be specific and actionable. Name actual topics, formats, entities.
- If trend data is stale, note it as such.
- Keep total output under 1500 tokens.
- No emojis. No preamble.
"""


def synthesize(
    system_prompt: str,
    assembled_summary: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1500,
) -> tuple[str, float, int, int]:
    """
    Call Claude with the assembled summary.
    Returns (response_text, cost_usd, input_tokens, output_tokens).
    """
    client = anthropic.Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": assembled_summary}],
    )

    text = response.content[0].text if response.content else ""
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    # Rough cost estimate
    # Sonnet: ~$3/$15 per million input/output tokens
    # Haiku: ~$0.25/$1.25 per million
    cost_usd = (input_tokens * 3.0 + output_tokens * 15.0) / 1_000_000
    if "haiku" in model.lower():
        cost_usd = (input_tokens * 0.25 + output_tokens * 1.25) / 1_000_000

    return text, cost_usd, input_tokens, output_tokens


def build_system_prompt(profile: dict) -> str:
    parts = []
    for key in ("tone", "interests", "context", "notes"):
        val = profile.get(key, "(not configured)")
        parts.append(f"## {key}.md\n{val}")
    parts.append(OUTPUT_FORMAT_CONTRACT)
    return "\n\n".join(parts)
