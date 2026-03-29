"""Tweet variant generator for `sable write`."""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sable.roster.manager import require_account
from sable.shared.api import build_account_context, call_claude_json

logger = logging.getLogger(__name__)


@dataclass
class TweetVariant:
    text: str
    structural_move: str
    format_fit_score: float
    notes: str = ""


@dataclass
class WriteResult:
    variants: list[TweetVariant]
    anatomy_ref: Optional[str] = None  # e.g. "contrarian_stat + counter-intuitive_payoff, 3.8x lift"
    vault_hint: Optional[str] = None   # suggested vault search command


def _load_format_trends(org: str, conn: sqlite3.Connection) -> dict[str, dict]:
    """Load format trend results from an open meta.db connection.

    Mirrors account_report._load_niche_lifts but returns all buckets and does
    not filter by days (caller manages the connection and query window upstream).
    Returns {} if no scanned tweets or import fails.
    """
    try:
        import json as _json
        from sable.pulse.meta.baselines import _rows_to_normalized
        from sable.pulse.meta.trends import analyze_all_formats

        raw_rows = conn.execute(
            """SELECT * FROM scanned_tweets
               WHERE org = ? AND total_lift IS NOT NULL
               ORDER BY posted_at DESC""",
            (org,),
        ).fetchall()

        if not raw_rows:
            return {}

        rows: list[dict] = []
        for row in raw_rows:
            d = dict(row)
            d["attributes"] = _json.loads(d.get("attributes_json") or "[]")
            rows.append(d)

        normalized = _rows_to_normalized(rows)
        if not normalized:
            return {}

        tweets_by_bucket: dict[str, list] = {}
        for tweet in normalized:
            tweets_by_bucket.setdefault(tweet.format_bucket, []).append(tweet)

        empty_baselines: dict[str, tuple] = {b: (None, None) for b in tweets_by_bucket}
        trend_results = analyze_all_formats(
            org=org,
            tweets_by_bucket=tweets_by_bucket,
            baselines=empty_baselines,
            baseline_days_available=0,
        )
        return {
            bucket: {
                "current_lift": tr.current_lift,
                "trend_status": tr.trend_status,
                "confidence": tr.confidence,
            }
            for bucket, tr in trend_results.items()
        }
    except Exception as e:
        logger.warning("_load_format_trends failed for org=%r: %s", org, e, exc_info=True)
        return {}


def _select_best_format(org: str, conn: sqlite3.Connection) -> str:
    """Return highest-lift active format bucket. Falls back to 'standalone_text'."""
    trends = _load_format_trends(org, conn)
    if not trends:
        return "standalone_text"
    best = max(trends, key=lambda b: trends[b].get("current_lift") or 0.0)
    return best


def _get_format_context(
    org: str,
    format_bucket: str,
    conn: sqlite3.Connection,
) -> tuple[str, list[dict]]:
    """Return (trend_summary_str, structural_examples) for the given format bucket.

    trend_summary_str: human-readable line for the prompt header.
    structural_examples: up to 5 high-lift tweets (dicts with text, total_lift, author_handle).
    """
    trends = _load_format_trends(org, conn)
    bucket_data = trends.get(format_bucket, {})

    lift = bucket_data.get("current_lift")
    status = bucket_data.get("trend_status") or "unknown"
    confidence = bucket_data.get("confidence") or "?"

    if lift is not None:
        trend_summary = (
            f"{format_bucket} {status} at {lift:.1f}x "
            f"(confidence {confidence}, based on niche scan)"
        )
    else:
        trend_summary = f"{format_bucket} (no recent niche data)"

    # Top high-lift examples as structural models
    rows = conn.execute(
        """SELECT text, total_lift, author_handle
           FROM scanned_tweets
           WHERE org = ? AND format_bucket = ? AND total_lift >= 2.5
                 AND posted_at >= datetime('now', '-30 days')
           ORDER BY total_lift DESC
           LIMIT 5""",
        (org, format_bucket),
    ).fetchall()
    examples = [dict(r) for r in rows]

    return trend_summary, examples


def _get_vault_context(
    topic: Optional[str],
    vault_path: Optional[Path],
    org: str,
) -> Optional[str]:
    """Return a 1-sentence vault note summary for the topic, or None.

    Uses search_vault with SearchFilters(depth='intro'). Returns the top result's
    note title + reason string, or None if topic/vault unavailable or search fails.
    """
    if not topic or not vault_path or not vault_path.exists():
        return None
    try:
        from sable.vault.search import search_vault, SearchFilters
        results = search_vault(
            topic, vault_path, org, filters=SearchFilters(depth="intro")
        )
        if not results:
            return None
        top = results[0]
        title = top.note.get("title") or top.id
        return f"Vault context: {title} — {top.reason}"
    except Exception as e:
        logger.warning("_get_vault_context failed for topic=%r: %s", topic, e, exc_info=True)
        return None


def _load_viral_anatomy_patterns(
    org: str,
    format_bucket: str,
    conn: sqlite3.Connection,
    min_lift: float = 2.5,
    limit: int = 5,
) -> tuple[list[dict], Optional[str]]:
    """Load and parse viral anatomy patterns from meta.db for prompt injection.

    Returns (patterns, anatomy_ref_str).
    patterns: list of dicts with hook_type, structural_move, payoff_mechanism, total_lift.
    anatomy_ref_str: human-readable reference for display, or None if no usable data.
    Falls back gracefully if table missing, rows absent, or JSON malformed.
    """
    try:
        rows = conn.execute(
            """SELECT total_lift, anatomy_json
               FROM viral_anatomies
               WHERE org = ? AND format_bucket = ? AND total_lift >= ?
                 AND analyzed_at >= datetime('now', '-30 days')
               ORDER BY total_lift DESC
               LIMIT ?""",
            (org, format_bucket, min_lift, limit),
        ).fetchall()
    except Exception as e:
        logger.warning("_load_viral_anatomy_patterns: query failed: %s", e)
        return [], None

    patterns: list[dict] = []
    for row in rows:
        try:
            anatomy = json.loads(row["anatomy_json"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        pattern = {
            "total_lift": row["total_lift"],
            "hook_type": anatomy.get("hook_type", ""),
            "structural_move": anatomy.get("structural_move", ""),
            "payoff_mechanism": anatomy.get("payoff_mechanism", ""),
        }
        patterns.append(pattern)

    if not patterns:
        return [], None

    # Human-readable ref from top pattern (for display in write output)
    top = patterns[0]
    ref_parts = [c for c in [top.get("hook_type"), top.get("payoff_mechanism")] if c]
    if not ref_parts and top.get("structural_move"):
        ref_parts = [top["structural_move"]]
    anatomy_ref = (
        f"{' + '.join(ref_parts)}, {top['total_lift']:.1f}x lift"
        if ref_parts else None
    )
    return patterns, anatomy_ref


def generate_tweet_variants(
    handle: str,
    org: str,
    format_bucket: Optional[str],
    topic: Optional[str],
    source_url: Optional[str],
    num_variants: int,
    meta_db_path: Optional[Path],
    vault_root: Optional[Path],
    watchlist_wire: bool = False,
    use_anatomy: bool = True,
) -> WriteResult:
    """Assemble context, call Claude, return WriteResult with variants and metadata."""
    acc = require_account(handle)
    resolved_org = org or acc.org
    account_context = build_account_context(acc)

    anatomy_ref: Optional[str] = None
    vault_hint: Optional[str] = None
    conn: Optional[sqlite3.Connection] = None
    try:
        if meta_db_path and meta_db_path.exists():
            conn = sqlite3.connect(str(meta_db_path))
            conn.row_factory = sqlite3.Row

        resolved_bucket = format_bucket
        if resolved_bucket is None:
            resolved_bucket = (
                _select_best_format(resolved_org, conn) if conn else "standalone_text"
            )

        if conn is not None:
            trend_summary, examples = _get_format_context(resolved_org, resolved_bucket, conn)
        else:
            trend_summary = f"{resolved_bucket} (no recent niche data)"
            examples = []

        vault_context = _get_vault_context(topic, vault_root, resolved_org)

        # Watchlist wire: inject top niche signals into prompt if requested
        niche_wire_block = ""
        if watchlist_wire:
            try:
                from sable.pulse.meta.db import get_top_topic_signals as _get_signals
                wire_signals = _get_signals(resolved_org, limit=3, min_unique_authors=1,
                                            conn=conn)
                if wire_signals:
                    terms = ", ".join(s["term"] for s in wire_signals)
                    niche_wire_block = f"\nTrending niche topics to consider: {terms}"
            except Exception as e:
                logger.warning("watchlist_wire fetch failed: %s", e)

        # Viral anatomy patterns: inject structural DNA from highest-lift tweets
        anatomy_block = ""
        if use_anatomy and conn is not None:
            patterns, anatomy_ref = _load_viral_anatomy_patterns(
                resolved_org, resolved_bucket, conn
            )
            if patterns:
                lines = []
                for p in patterns:
                    parts = []
                    if p.get("hook_type"):
                        parts.append(f"hook: {p['hook_type']}")
                    if p.get("structural_move"):
                        parts.append(f"move: {p['structural_move']}")
                    if p.get("payoff_mechanism"):
                        parts.append(f"payoff: {p['payoff_mechanism']}")
                    if parts:
                        lines.append(f"  • [{p['total_lift']:.1f}x] " + " | ".join(parts))
                if lines:
                    anatomy_block = (
                        "\nStructural patterns from highest-performing content in this niche"
                        " (use as inspiration, not templates):\n" + "\n".join(lines) + "\n"
                    )

        # Vault search suggestion (keyword hint, zero cost)
        if topic and vault_root and vault_root.exists():
            safe_topic = topic.replace("'", "").replace('"', "")
            vault_hint = f"sable vault search '{safe_topic}' --available-for {handle}"

        # Prompt assembly
        if examples:
            example_lines = []
            for i, ex in enumerate(examples, 1):
                lift = ex.get("total_lift") or 0.0
                author = ex.get("author_handle") or "?"
                text = ex.get("text") or ""
                example_lines.append(f"{i}. [{author}, {lift:.1f}x lift]\n{text}")
            examples_block = "\n\n".join(example_lines)
        else:
            examples_block = "(no recent high-lift examples available for this format)"

        source_block = f"\nSource tweet / quote target: {source_url}" if source_url else ""
        vault_block = f"\n{vault_context}" if vault_context else ""
        topic_str = topic or "choose from account interests"

        system_prompt = (
            "You are a ghost-writer for a crypto Twitter account. "
            "The account profile is:\n\n"
            f"{account_context}\n\n"
            "Write tweet variants that sound exactly like this account "
            "— not generic crypto content."
        )
        user_prompt = (
            f"Format target: {resolved_bucket} (currently {trend_summary})\n\n"
            f"Examples of what's performing at {resolved_bucket} right now "
            f"(study structure, not content):\n{examples_block}\n\n"
            f"{anatomy_block}"
            f"Topic to write about: {topic_str}"
            f"{source_block}"
            f"{vault_block}"
            f"{niche_wire_block}\n\n"
            f"Generate {num_variants} tweet variants. For each:\n"
            "- Write the tweet text (respect Twitter's 280-char limit for standalone; "
            "280 per tweet for threads)\n"
            "- Identify the structural move you're making "
            '(e.g. "contrarian claim + specific number")\n'
            "- Rate format fit 1-10 based on how well it matches the example structure patterns\n\n"
            'Return JSON:\n{\n  "variants": [\n    {\n'
            '      "text": "...",\n'
            '      "structural_move": "...",\n'
            '      "format_fit_score": 8.5,\n'
            '      "notes": "optional one-liner about the approach"\n'
            "    }\n  ]\n}"
        )

        raw = call_claude_json(
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=2048,
            call_type="write_variants",
            org_id=resolved_org,
        )

        # Parse response
        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(raw)
            variant_dicts = data.get("variants", [])
            if not isinstance(variant_dicts, list):
                raise ValueError(f"Expected 'variants' list, got {type(variant_dicts)}")
            variant_list = [
                TweetVariant(
                    text=str(v.get("text", "")),
                    structural_move=str(v.get("structural_move", "")),
                    format_fit_score=float(v.get("format_fit_score", 0.0)),
                    notes=str(v.get("notes", "")),
                )
                for v in variant_dicts
            ]
            return WriteResult(
                variants=variant_list,
                anatomy_ref=anatomy_ref,
                vault_hint=vault_hint,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("generate_tweet_variants: JSON parse failed: %s", e)
            return WriteResult(variants=[], anatomy_ref=anatomy_ref, vault_hint=vault_hint)

    finally:
        if conn is not None:
            conn.close()
