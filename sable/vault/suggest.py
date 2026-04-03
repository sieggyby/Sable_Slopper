"""Reply suggestion engine — matches vault content to tweets."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from sable.vault.config import VaultConfig
from sable.vault.search import SearchFilters, search_vault


@dataclass
class ReplySuggestion:
    content_id: str
    content_title: str
    content_type: str
    content_path: str
    account: str
    relevance_score: int
    relevance_reason: str
    reply_draft: str = ""


def suggest_replies(
    tweet_text: str,
    org: str,
    account: Optional[str],
    vault_path: Path,
    config: Optional[VaultConfig] = None,
) -> list[ReplySuggestion]:
    """Find vault content relevant to a tweet and generate reply drafts."""
    if config is None:
        from sable.vault.config import load_vault_config
        config = load_vault_config()

    filters = SearchFilters(
        reply_context=tweet_text,
        available_for=account,
    )
    results = search_vault(tweet_text, vault_path, org, filters=filters, config=config)

    if not results:
        return []

    top = results[: config.max_suggestions]

    # Build suggestions (one per result)
    suggestions = []
    for r in top:
        note = r.note
        suggestions.append(ReplySuggestion(
            content_id=r.id,
            content_title=_note_title(note),
            content_type=note.get("type", ""),
            content_path=note.get("output", ""),
            account=account or note.get("account", ""),
            relevance_score=r.score,
            relevance_reason=r.reason,
        ))

    # Draft reply texts
    suggestions = _draft_reply_texts(suggestions, tweet_text, org, account, config)
    return suggestions


def _note_title(note: dict) -> str:
    """Derive a human-readable title from a content note."""
    t = note.get("type", "")
    if t == "clip":
        return f"Clip: {note.get('caption', note.get('id', ''))}"
    elif t == "meme":
        return f"Meme: {note.get('template', '')} — {note.get('topic', '')}"
    elif t == "faceswap":
        return f"Faceswap: {note.get('id', '')}"
    elif t == "explainer":
        return f"Explainer: {note.get('topic', '')}"
    return note.get("id", "?")


def _draft_reply_texts(
    suggestions: list[ReplySuggestion],
    tweet_text: str,
    org: str,
    account: Optional[str],
    config: VaultConfig,
) -> list[ReplySuggestion]:
    """Generate reply draft text for each suggestion via Claude."""
    if not suggestions:
        return suggestions

    from sable.shared.api import call_claude_json

    # Build account context if account specified
    acc_context = ""
    if account:
        try:
            from sable.roster.manager import require_account
            from sable.shared.api import build_account_context
            acc = require_account(account)
            acc_context = build_account_context(acc)
        except Exception as e:
            logger.warning("Could not load account context for %s: %s", account, e)

    items = [
        {
            "content_id": s.content_id,
            "content_title": s.content_title,
            "content_type": s.content_type,
            "relevance_reason": s.relevance_reason,
        }
        for s in suggestions
    ]

    prompt = f"""You are writing crypto Twitter reply drafts.

{acc_context}

Original tweet: "{tweet_text}"

For each piece of content below, write a short reply tweet (under 280 chars) that shares
the content naturally in response to the tweet. Sound like the account, not a bot.

Content items:
{json.dumps(items, indent=2)}

Return a JSON array of objects with:
- content_id: (same as input)
- reply_draft: the reply tweet text

No extra text."""

    try:
        raw = call_claude_json(prompt, org_id=org if org else None)
        drafts_data = json.loads(raw) if isinstance(raw, str) else raw

        if isinstance(drafts_data, dict) and "drafts" in drafts_data:
            drafts_data = drafts_data["drafts"]

        draft_map = {d["content_id"]: d.get("reply_draft", "") for d in (drafts_data or []) if isinstance(d, dict)}

        for s in suggestions:
            s.reply_draft = draft_map.get(s.content_id, "")
    except Exception as e:
        logger.warning("Reply draft generation failed: %s", e)

    return suggestions


def fetch_tweet_text(tweet_url: str) -> str:
    """Fetch tweet text from a URL using SocialData API."""
    import re
    from sable.shared.socialdata import socialdata_get

    # Extract tweet ID from URL
    match = re.search(r"/status/(\d+)", tweet_url)
    if not match:
        raise ValueError(f"Cannot extract tweet ID from URL: {tweet_url}")
    tweet_id = match.group(1)

    data = socialdata_get(f"/twitter/tweets/{tweet_id}", timeout=15)
    return data.get("full_text") or data.get("text") or ""
