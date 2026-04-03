"""Vault search engine — frontmatter filtering + Claude ranking."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sable.vault.config import VaultConfig
from sable.vault.notes import load_all_notes

logger = logging.getLogger(__name__)


@dataclass
class SearchFilters:
    depth: Optional[str] = None          # intro | intermediate | advanced
    content_type: Optional[str] = None   # clip | meme | faceswap | explainer
    format: Optional[str] = None
    available_for: Optional[str] = None  # handle — exclude if in posted_by
    reply_context: Optional[str] = None  # tweet text for reply suggestion mode


@dataclass
class SearchResult:
    id: str
    score: int
    reason: str
    note: dict


def search_vault(
    query: str,
    vault_path: Path,
    org: str,
    filters: Optional[SearchFilters] = None,
    config: Optional[VaultConfig] = None,
) -> list[SearchResult]:
    """Search vault content notes.

    Returns ranked SearchResult list.
    """
    if config is None:
        from sable.vault.config import load_vault_config
        config = load_vault_config()
    if filters is None:
        filters = SearchFilters()

    candidates = load_candidates(vault_path)
    candidates = _apply_hard_filters(candidates, filters)

    if not candidates:
        return []

    if len(candidates) <= 50:
        try:
            return claude_rank(query, candidates, filters, config, org=org)
        except Exception as e:
            logger.warning("Claude ranking failed, using keyword fallback: %s", e, exc_info=True)
            prescored = keyword_prescore(query, candidates)
            return [
                SearchResult(id=n.get("id", "?"), score=s, reason="keyword match", note=n)
                for n, s in prescored[:config.max_suggestions]
            ]
    else:
        prescored = keyword_prescore(query, candidates)
        top50_notes = [note for note, _score in prescored[:50]]  # unwrap tuples
        try:
            return claude_rank(query, top50_notes, filters, config, org=org)
        except Exception as e:
            logger.warning("Claude ranking failed, using keyword fallback: %s", e, exc_info=True)
            # Fallback: return keyword-scored results
            return [
                SearchResult(id=n.get("id", "?"), score=s, reason="keyword match", note=n)
                for n, s in prescored[:config.max_suggestions]
            ]


def load_candidates(vault_path: Path) -> list[dict]:
    """Load all content note frontmatter."""
    return load_all_notes(vault_path)


def keyword_prescore(query: str, candidates: list[dict]) -> list[tuple[dict, int]]:
    """Simple keyword overlap scoring. Returns list of (note, score) sorted desc."""
    query_tokens = set(query.lower().split())

    scored = []
    for note in candidates:
        score = 0
        # Check topic, keywords, caption, questions_answered
        text_fields = [
            note.get("topic", ""),
            note.get("caption", ""),
            " ".join(note.get("keywords", [])),
            " ".join(note.get("questions_answered", [])),
            note.get("script_preview", ""),
            note.get("depth", ""),
            note.get("tone", ""),
        ]
        combined = " ".join(str(f) for f in text_fields).lower()
        for token in query_tokens:
            if token in combined:
                score += 1
        scored.append((note, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def claude_rank(
    query: str,
    candidates: list[dict],
    filters: SearchFilters,
    config: VaultConfig,
    org: str = "",
) -> list[SearchResult]:
    """Send top candidates to Claude for ranking."""
    from sable.shared.api import call_claude_json

    items = []
    for n in candidates:
        items.append({
            "id": n.get("id", ""),
            "type": n.get("type", ""),
            "account": n.get("account", ""),
            "topic": n.get("topic", "") or n.get("caption", ""),
            "topics": n.get("topics", []),
            "questions_answered": n.get("questions_answered", []),
            "depth": n.get("depth", ""),
            "tone": n.get("tone", ""),
            "keywords": n.get("keywords", []),
        })

    context = ""
    if filters.reply_context:
        context = f"\nThis is for replying to this tweet: \"{filters.reply_context}\""

    prompt = f"""You are a content strategist for a crypto Twitter community management firm.
Rank these content pieces by relevance to the query.{context}

Query: "{query}"

Content items:
{json.dumps(items, indent=2)}

For each relevant item (score >= 40), return:
- id: content id
- score: 0-100 relevance score
- reason: one-sentence explanation

Return a JSON array sorted by score descending. Only include items with score >= 40. No extra text."""

    raw = call_claude_json(prompt, org_id=org if org else None)
    ranked = json.loads(raw) if isinstance(raw, str) else raw

    if isinstance(ranked, dict) and "results" in ranked:
        ranked = ranked["results"]

    # Build note lookup
    note_map = {n.get("id", ""): n for n in candidates}

    results = []
    for r in (ranked or []):
        if not isinstance(r, dict):
            continue
        nid = r.get("id", "")
        if nid in note_map:
            results.append(SearchResult(
                id=nid,
                score=int(r.get("score", 0)),
                reason=r.get("reason", ""),
                note=note_map[nid],
            ))

    return results


def _apply_hard_filters(candidates: list[dict], filters: SearchFilters) -> list[dict]:
    """Apply hard filters before ranking."""
    result = []
    for n in candidates:
        if filters.depth and n.get("depth") != filters.depth:
            continue
        if filters.content_type and n.get("type") != filters.content_type:
            continue
        if filters.format and n.get("format") != filters.format:
            continue
        if filters.available_for:
            posted = [
                (p if isinstance(p, str) else p.get("account", ""))
                for p in (n.get("posted_by") or [])
            ]
            if filters.available_for in posted:
                continue
        result.append(n)
    return result
