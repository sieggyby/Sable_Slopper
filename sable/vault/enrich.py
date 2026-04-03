"""Claude batched topic tagging and question generation for vault content."""
from __future__ import annotations

import json
import logging
from typing import Optional

from sable.vault.config import VaultConfig

logger = logging.getLogger(__name__)


def enrich_batch(
    content_batch: list[dict],
    org_topics: list[str],
    config: Optional[VaultConfig] = None,
    org: str = "",
) -> list[dict]:
    """Enrich a batch of content items with topics, questions, depth, tone, keywords.

    Sends up to `config.enrich_batch_size` items per Claude call.
    Returns items with enrichment fields populated.
    On failure, returns items with enrichment_status='pending'.
    """
    if config is None:
        from sable.vault.config import load_vault_config
        config = load_vault_config()

    from sable.shared.api import call_claude_json

    results = list(content_batch)
    batch_size = config.enrich_batch_size

    for i in range(0, len(results), batch_size):
        chunk = results[i : i + batch_size]
        try:
            enriched = _enrich_chunk(chunk, org_topics, config, call_claude_json, org=org)
            for j, item in enumerate(enriched):
                results[i + j] = item
        except Exception as e:
            logger.warning("Enrichment chunk failed (items %d–%d): %s", i, i + len(chunk) - 1, e)
            for j in range(len(chunk)):
                results[i + j]["enrichment_status"] = "pending"

    return results


def _enrich_chunk(
    chunk: list[dict],
    org_topics: list[str],
    config: VaultConfig,
    call_fn,
    org: str = "",
) -> list[dict]:
    """Run one Claude call to enrich a chunk of items."""
    items_payload = []
    for item in chunk:
        preview = (
            item.get("script", "") or item.get("caption", "") or item.get("topic", "")
        )[:500]
        items_payload.append({
            "id": item.get("id", ""),
            "type": item.get("type", ""),
            "topic": item.get("topic", "") or item.get("title", ""),
            "template": item.get("template", ""),
            "preview": preview,
        })

    topics_hint = ", ".join(org_topics[:30]) if org_topics else "general crypto/web3"

    prompt = f"""You are a content analyst for a crypto Twitter community management firm.

Enrich each content item with metadata. Known org topics: {topics_hint}

Content items:
{json.dumps(items_payload, indent=2)}

For each item return:
- id: (same as input)
- topics: list of 1-5 topic slugs from org topics (or close matches)
- questions_answered: list of 1-3 questions this content answers (as strings)
- depth: one of "intro", "intermediate", "advanced"
- tone: one of "educational", "degen", "analytical", "hype", "neutral"
- keywords: list of 3-8 relevant keywords

Return a JSON array of enrichment objects, one per item. No extra text."""

    raw = call_fn(prompt, org_id=org if org else None)
    enriched_data = json.loads(raw) if isinstance(raw, str) else raw

    if isinstance(enriched_data, dict) and "items" in enriched_data:
        enriched_data = enriched_data["items"]

    enriched_map = {e["id"]: e for e in enriched_data if isinstance(e, dict)}

    output = []
    for item in chunk:
        result = dict(item)
        enrich = enriched_map.get(item.get("id", ""), {})
        result["topics"] = enrich.get("topics", [])
        result["questions_answered"] = enrich.get("questions_answered", [])
        result["depth"] = enrich.get("depth", "")
        result["tone"] = enrich.get("tone", "")
        result["keywords"] = enrich.get("keywords", [])
        result["enrichment_status"] = "done"
        output.append(result)

    return output
