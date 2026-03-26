"""Shared Anthropic client and account context builder."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import anthropic

from sable import config as cfg
from sable.roster.models import Account
from sable.roster.profiles import load_profiles, format_profiles_for_prompt
from sable.shared.pricing import compute_cost as _compute_cost_pricing


_client: Optional[anthropic.Anthropic] = None


@dataclass
class ClaudeCallResult:
    text: str
    cost_usd: float
    input_tokens: int
    output_tokens: int


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


def _compute_cost(usage, model: str) -> float:
    """Compute cost from API usage object and model name."""
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    return _compute_cost_pricing(input_tokens, output_tokens, model)


def call_claude(
    prompt: str,
    system: str = "",
    model: Optional[str] = None,
    max_tokens: int = 2048,
    org_id: Optional[str] = None,
    call_type: str = "unknown",
) -> str:
    """Simple single-turn Claude call. Returns text response."""
    return call_claude_with_usage(
        prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
        org_id=org_id,
        call_type=call_type,
    ).text


def call_claude_with_usage(
    prompt: str,
    system: str = "",
    model: Optional[str] = None,
    max_tokens: int = 2048,
    org_id: Optional[str] = None,
    call_type: str = "unknown",
) -> ClaudeCallResult:
    """Claude call wrapper that optionally enforces org budget and returns usage details."""
    client = get_client()
    if model is None:
        model = cfg.get("default_model", "claude-sonnet-4-6")

    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system

    conn = None
    budget_org_id: str | None = None
    if org_id is not None:
        from sable.platform.db import get_db
        from sable.platform.cost import check_budget, log_cost
        conn = get_db()
        check_budget(conn, org_id)
        budget_org_id = org_id

    try:
        response = client.messages.create(**kwargs)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cost_usd = _compute_cost(usage, model)

        if conn is not None and budget_org_id is not None:
            try:
                log_cost(conn, budget_org_id, call_type, cost_usd,
                         model=model,
                         input_tokens=input_tokens,
                         output_tokens=output_tokens)
            except Exception:
                pass
        text = response.content[0].text if response.content else ""
        return ClaudeCallResult(
            text=text,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    finally:
        if conn is not None:
            conn.close()


def call_claude_json(
    prompt: str,
    system: str = "",
    model: Optional[str] = None,
    max_tokens: int = 2048,
    org_id: Optional[str] = None,
    call_type: str = "unknown",
) -> str:
    """Call Claude expecting JSON output. Returns raw text (caller parses)."""
    json_system = (system + "\n\nRespond with valid JSON only. No markdown fences.").strip()
    return call_claude(prompt, system=json_system, model=model, max_tokens=max_tokens,
                       org_id=org_id, call_type=call_type)
