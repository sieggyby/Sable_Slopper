"""Claude API meme generation — injects full account context."""
from __future__ import annotations

import json
from typing import Optional

from sable.roster.models import Account
from sable.shared.api import build_account_context, call_claude_json
from sable.meme.templates import get_template, load_registry


def generate_meme_text(
    template_id: str,
    account: Account,
    topic: Optional[str] = None,
    vibe: Optional[str] = None,
    dry_run: bool = False,
    org_id: Optional[str] = None,
) -> dict[str, str]:
    """
    Generate text for a specific meme template using Claude.
    Returns {zone_id: text_string}.
    """
    template = get_template(template_id)
    account_context = build_account_context(account, profile_files=["tone", "interests"])

    zones_desc = "\n".join(
        f"  - {z['id']}: {z['label']}"
        for z in template.get("zones", [])
    )

    topic_line = f"Topic/angle: {topic}" if topic else "Choose a relevant crypto Twitter topic."
    vibe_line = f"Vibe: {vibe}" if vibe else ""

    prompt = f"""You are a meme copywriter for crypto Twitter.

{account_context}

## Meme Template: {template['name']}
{template.get('description', '')}

Template hint: {template.get('prompt_hint', '')}

## Text zones to fill:
{zones_desc}

## Instructions
{topic_line}
{vibe_line}

Write punchy, platform-native text for each zone. Match the account's voice exactly.
Keep each zone's text short — memes need to be readable at a glance.

Return JSON only:
{{
{chr(10).join(f'  "{z["id"]}": "<text>"' for z in template.get("zones", []))}
}}
"""

    if dry_run:
        return {z["id"]: f"[DRY RUN: {z['label']}]" for z in template.get("zones", [])}

    raw = call_claude_json(prompt, max_tokens=512, org_id=org_id,
                           call_type="meme_generate", budget_check=False)

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude returned invalid JSON: {e}\nRaw: {raw[:300]}")


def suggest_template(
    account: Account,
    topic: Optional[str] = None,
    org_id: Optional[str] = None,
) -> str:
    """Ask Claude which template best fits this account + topic."""
    templates = load_registry()
    account_context = build_account_context(account, profile_files=["tone", "interests"])

    templates_desc = "\n".join(
        f"  - {t['id']}: {t['name']} — {t.get('prompt_hint', '')}"
        for t in templates
    )

    prompt = f"""You are a meme strategist for crypto Twitter.

{account_context}

## Available templates:
{templates_desc}

## Task
{"Topic: " + topic if topic else "Pick a template that would work well for a spontaneous post."}

Return the template ID that best matches this account's voice and the topic.
Return only the template ID string, nothing else.
"""

    result = call_claude_json(prompt, max_tokens=64, org_id=org_id,
                              call_type="meme_suggest", budget_check=False)
    # Strip quotes if present
    return result.strip().strip('"\'')


def generate_batch(
    account: Account,
    num_memes: int = 5,
    topics: Optional[list[str]] = None,
    org_id: Optional[str] = None,
) -> list[dict]:
    """
    Generate a batch of meme suggestions (template + text) for an account.
    Returns list of {template_id, texts, topic}.
    """
    account_context = build_account_context(account, profile_files=["tone", "interests"])
    templates = load_registry()
    templates_desc = "\n".join(
        f"  - {t['id']}: {t['name']} ({t.get('prompt_hint', '')})"
        for t in templates
    )

    topics_line = f"Topics to cover: {', '.join(topics)}" if topics else "Choose diverse crypto topics."

    prompt = f"""You are a meme content strategist for crypto Twitter.

{account_context}

## Available templates:
{templates_desc}

## Task
Generate {num_memes} meme ideas for this account.
{topics_line}

For each meme, choose a template and write all zone texts.

Return JSON array:
[
  {{
    "template_id": "<id>",
    "topic": "<topic>",
    "texts": {{<zone_id>: "<text>", ...}}
  }},
  ...
]
"""

    raw = call_claude_json(prompt, max_tokens=2048, org_id=org_id,
                           call_type="meme_batch", budget_check=False)
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(raw)
        if isinstance(result, dict):
            result = result.get("memes", list(result.values())[0] if result else [])
        return result[:num_memes]
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude returned invalid JSON: {e}\nRaw: {raw[:500]}")
