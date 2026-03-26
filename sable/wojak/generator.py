"""Claude-powered wojak scene generator — selects wojaks and writes scene spec."""
from __future__ import annotations

import json
from typing import Optional

from sable.roster.models import Account
from sable.shared.api import build_account_context, call_claude_json
from sable.wojak.library import load_library
from sable.wojak.compositor import VALID_POSITIONS


def generate_scene(
    account: Account,
    topic: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Ask Claude to select wojaks and compose a scene spec.

    Returns:
        {
            "layers": [{"wojak_id": str, "position": str, "label": str}, ...],
            "caption": str
        }
    """
    library = load_library()
    account_context = build_account_context(account, profile_files=["tone", "interests"])

    wojak_list = "\n".join(
        f"  - id: {w['id']}\n"
        f"    name: {w['name']}\n"
        f"    emotion: {w['emotion']}\n"
        f"    tags: {', '.join(w.get('tags', []))}\n"
        f"    description: {w.get('description', '')}"
        for w in library
    )

    positions_str = ", ".join(VALID_POSITIONS)
    topic_line = f"Topic/angle: {topic}" if topic else "Choose a relevant crypto Twitter topic."

    prompt = f"""You are a meme strategist composing wojak scenes for crypto Twitter.

{account_context}

## Available Wojak Characters:
{wojak_list}

## Scene Composition Rules:
- Choose 1–3 wojaks that create a funny, relatable, or insightful scene
- Valid positions: {positions_str}
- Each wojak gets a short label (1–5 words) beneath it
- Optional: add a caption at top of image (1 sentence max, can be empty string)
- The scene should match the account's voice and the topic

## Task:
{topic_line}

Design a wojak scene that would work well on crypto Twitter.
Pick the best wojak characters, assign positions, write punchy labels.

Return JSON only:
{{
  "layers": [
    {{"wojak_id": "<id>", "position": "<position>", "label": "<short label>"}},
    ...
  ],
  "caption": "<optional top caption or empty string>"
}}
"""

    if dry_run:
        # Return a placeholder scene for dry runs
        if library:
            return {
                "layers": [
                    {"wojak_id": library[0]["id"], "position": "left", "label": "[DRY RUN left]"},
                    {"wojak_id": library[min(4, len(library) - 1)]["id"], "position": "right", "label": "[DRY RUN right]"},
                ],
                "caption": f"[DRY RUN: {topic or 'scene'}]",
            }
        return {"layers": [], "caption": "[DRY RUN]"}

    raw = call_claude_json(prompt, max_tokens=512)  # budget-exempt: wojak generation has no org context

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude returned invalid JSON: {e}\nRaw: {raw[:300]}")

    # Validate structure
    if "layers" not in result:
        raise RuntimeError(f"Claude response missing 'layers' key. Got: {result}")

    for layer in result["layers"]:
        if "position" in layer and layer["position"] not in VALID_POSITIONS:
            layer["position"] = "center"

    result.setdefault("caption", "")

    return result
