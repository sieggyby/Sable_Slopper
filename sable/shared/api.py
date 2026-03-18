"""Shared Anthropic client and account context builder."""
from __future__ import annotations

from typing import Optional
import anthropic

from sable import config as cfg
from sable.roster.models import Account
from sable.roster.profiles import load_profiles, format_profiles_for_prompt


_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = cfg.require_key("anthropic_api_key")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def build_account_context(
    account: Account,
    profile_files: Optional[list[str]] = None,
) -> str:
    """
    Build a combined context string from YAML persona fields + markdown profile files.
    Injected into every Claude prompt that references an account.
    """
    if profile_files is None:
        profile_files = ["tone", "interests", "context", "notes"]

    lines = [
        f"# Account: {account.handle}",
        f"Display name: {account.display_name or account.handle}",
        f"Org: {account.org or 'independent'}",
    ]

    # Structured persona fields
    p = account.persona
    if p.archetype:
        lines.append(f"Archetype: {p.archetype}")
    if p.voice:
        lines.append(f"Voice: {p.voice}")
    if p.topics:
        lines.append(f"Topics: {', '.join(p.topics)}")
    if p.avoid:
        lines.append(f"Avoid: {', '.join(p.avoid)}")

    # Content settings
    c = account.content
    lines.append(
        f"Content style: clip={c.clip_style}, meme={c.meme_style}, "
        f"captions={c.caption_style}, brainrot_energy={c.brainrot_energy}"
    )

    # Learned preferences from pulse feedback
    if account.learned_preferences:
        lines.append("\n## Learned Preferences (from performance data)")
        for k, v in account.learned_preferences.items():
            lines.append(f"  {k}: {v}")

    yaml_context = "\n".join(lines)

    # Markdown profiles
    profiles = load_profiles(account.handle, profile_files)
    profile_context = format_profiles_for_prompt(profiles)

    parts = [yaml_context]
    if profile_context:
        parts.append(profile_context)

    return "\n\n".join(parts)


def call_claude(
    prompt: str,
    system: str = "",
    model: Optional[str] = None,
    max_tokens: int = 2048,
) -> str:
    """Simple single-turn Claude call. Returns text response."""
    client = get_client()
    if model is None:
        model = cfg.get("default_model", "claude-sonnet-4-6")

    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    return response.content[0].text


def call_claude_json(
    prompt: str,
    system: str = "",
    model: Optional[str] = None,
    max_tokens: int = 2048,
) -> str:
    """Call Claude expecting JSON output. Returns raw text (caller parses)."""
    json_system = (system + "\n\nRespond with valid JSON only. No markdown fences.").strip()
    return call_claude(prompt, system=json_system, model=model, max_tokens=max_tokens)
