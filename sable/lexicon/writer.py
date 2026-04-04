"""Lexicon writer — Claude interpretation and vault report generation."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def interpret_terms(
    terms: list[dict],
    org: str,
) -> list[dict]:
    """Classify top terms via a single Claude call.

    Adds 'category' and 'gloss' fields to each term dict.
    Returns the enriched list (max 25 terms sent to Claude).
    """
    from sable.shared.api import call_claude_json

    if not terms:
        return terms

    # Budget check — SableError must propagate (BUDGET_EXCEEDED is fatal)
    from sable.platform.db import get_db
    from sable.platform.cost import check_budget
    platform_conn = get_db()
    try:
        check_budget(platform_conn, org)
    finally:
        platform_conn.close()

    batch = terms[:25]
    term_list = "\n".join(f"- {t['term']}" for t in batch)
    prompt = (
        f"Community: {org}\n\n"
        f"These terms were extracted from community watchlist tweets. "
        f"Classify each as one of: insider_slang, project_term, topic_reference, noise.\n"
        f"Also provide a one-line gloss (definition).\n\n"
        f"Terms:\n{term_list}\n\n"
        f'Return JSON array: [{{"term": "...", "category": "...", "gloss": "..."}}]'
    )

    try:
        raw = call_claude_json(prompt, call_type="lexicon_interpret", org_id=org,
                               budget_check=False)
        parsed = json.loads(raw)
        # Handle wrapped response: {"terms": [...]} or {"results": [...]}
        if isinstance(parsed, dict):
            for key in ("terms", "results", "data"):
                if key in parsed and isinstance(parsed[key], list):
                    parsed = parsed[key]
                    break
            else:
                logger.warning("Claude returned dict without recognized list key: %s", list(parsed.keys()))
                parsed = []
        if isinstance(parsed, list):
            lookup = {item["term"].lower(): item for item in parsed if "term" in item}
            for t in batch:
                match = lookup.get(t["term"].lower(), {})
                t["category"] = match.get("category", "unknown")
                t["gloss"] = match.get("gloss", "")
    except Exception as e:
        from sable.platform.errors import SableError
        if isinstance(e, SableError):
            raise
        logger.warning("Claude lexicon interpretation failed: %s", e)
        for t in batch:
            t.setdefault("category", "unknown")
            t.setdefault("gloss", "")

    return terms


def render_report(terms: list[dict], org: str, vault_path: Path) -> Path:
    """Write lexicon report to vault as markdown."""
    from sable.shared.files import atomic_write

    lines = [
        "---",
        "type: lexicon_report",
        f"org: {org}",
        "---",
        "",
        f"# Community Lexicon — {org}",
        "",
    ]

    if not terms:
        lines.append("No community-specific terms detected yet.")
    else:
        lines.append("| Term | Category | Gloss | LSR |")
        lines.append("|------|----------|-------|-----|")
        for t in terms:
            cat = t.get("category", "")
            gloss = t.get("gloss", "")
            lsr = t.get("lsr", 0)
            lines.append(f"| {t['term']} | {cat} | {gloss} | {lsr:.3f} |")

    lines.append("")

    report_path = vault_path / "lexicon_report.md"
    atomic_write(report_path, "\n".join(lines))
    return report_path
