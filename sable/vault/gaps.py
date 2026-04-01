"""Coverage gap analysis per topic."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sable.vault.notes import load_all_notes
from sable.vault.topics import list_topics


# ---------------------------------------------------------------------------
# Signal-gap analysis (requires meta.db topic_signals)
# ---------------------------------------------------------------------------

@dataclass
class VaultSignalGap:
    term: str
    signal_score: float
    avg_lift: float
    acceleration: float
    unique_authors: int
    recommended_type: str  # heuristic


def _recommend_type(term: str) -> str:
    """Simple heuristic: assign a recommended content type based on term keywords."""
    term_lower = term.lower()
    if any(kw in term_lower for kw in ("how", "what", "why", "guide", "explain", "tutorial")):
        return "explainer"
    if any(kw in term_lower for kw in ("meme", "joke", "funny", "lol")):
        return "meme"
    if any(kw in term_lower for kw in ("clip", "video", "watch")):
        return "clip"
    return "standalone_text"


def compute_signal_gaps(
    org: str,
    vault_path: Optional[Path] = None,
    meta_db: Optional[sqlite3.Connection] = None,
    top_n: int = 10,
    min_unique_authors: int = 2,
) -> list[VaultSignalGap]:
    """Return signal terms with no vault coverage, sorted by signal score desc.

    Parameters
    ----------
    org:
        Client org string.
    vault_path:
        Optional path to the vault root. If None, uses sable.shared.paths.vault_dir(org).
    meta_db:
        Optional open sqlite3.Connection to meta.db. When None the function
        attempts to open the default meta.db via get_top_topic_signals(); if no
        meta.db exists it returns [].
    top_n:
        Maximum number of gaps to return.
    min_unique_authors:
        Minimum unique_authors threshold passed to get_top_topic_signals.
    """
    # Lazy import to avoid circular deps
    from sable.pulse.meta.db import get_top_topic_signals

    # Resolve vault path
    if vault_path is None:
        try:
            from sable.shared.paths import vault_dir
            vault_path = vault_dir(org)
        except Exception:
            vault_path = None

    # Build covered terms from vault notes
    covered_terms: set[str] = set()
    if vault_path is not None:
        try:
            notes = load_all_notes(vault_path)
        except Exception:
            notes = []
        for note in notes:
            for t in (note.get("topics") or []):
                if t:
                    covered_terms.add(str(t).lower())
            for kw in (note.get("keywords") or []):
                if kw:
                    covered_terms.add(str(kw).lower())
            topic_field = note.get("topic")
            if topic_field:
                covered_terms.add(str(topic_field).lower())
            caption_field = note.get("caption")
            if caption_field:
                covered_terms.add(str(caption_field).lower())

    # Fetch top signals — pass conn if meta_db provided
    try:
        if meta_db is not None:
            signals = get_top_topic_signals(
                org,
                limit=100,
                min_unique_authors=min_unique_authors,
                conn=meta_db,
            )
        else:
            # get_top_topic_signals will call get_conn() which opens the default meta.db
            # If that file doesn't exist, sqlite3 will create an empty DB with no data
            try:
                from sable.shared.paths import meta_db_path as _meta_db_path
                db_path = _meta_db_path()
                if not db_path.exists():
                    return []
            except Exception:
                return []
            signals = get_top_topic_signals(
                org,
                limit=100,
                min_unique_authors=min_unique_authors,
            )
    except Exception:
        return []

    if not signals:
        return []

    # Identify gaps: signal term not covered by any vault term (substring match)
    gaps: list[VaultSignalGap] = []
    for sig in signals:
        term = sig["term"]
        term_lower = term.lower()
        covered = any(
            term_lower in ct or ct in term_lower
            for ct in covered_terms
        )
        if not covered:
            avg_lift = sig.get("avg_lift") or 0.0
            acceleration = sig.get("acceleration") or 0.0
            unique_authors = sig.get("unique_authors") or 1
            score = avg_lift * max(acceleration, 0.1) * max(unique_authors, 1)
            gaps.append(VaultSignalGap(
                term=term,
                signal_score=round(score, 4),
                avg_lift=avg_lift,
                acceleration=acceleration,
                unique_authors=unique_authors,
                recommended_type=_recommend_type(term),
            ))

    gaps.sort(key=lambda g: g.signal_score, reverse=True)
    return gaps[:top_n]


def render_signal_gaps(gaps: list[VaultSignalGap], org: str) -> str:
    """Render signal gaps as a plain-text table (Rich-compatible)."""
    if not gaps:
        return f"[green]No niche-gaps found for {org} — vault covers all trending signals.[/green]"

    lines = [f"Niche-Gap Signals — {org}\n"]
    header = f"{'#':<4}{'Term':<30}{'Score':>8}{'Lift':>8}{'Accel':>8}{'Authors':>9}{'Type':<18}"
    lines.append(header)
    lines.append("-" * len(header))
    for i, g in enumerate(gaps, 1):
        lines.append(
            f"{i:<4}{g.term:<30}{g.signal_score:>8.2f}{g.avg_lift:>8.2f}"
            f"{g.acceleration:>8.2f}{g.unique_authors:>9}  {g.recommended_type}"
        )
    return "\n".join(lines)


def analyze_gaps(org: str, vault_path: Path) -> list[dict]:
    """Return gap analysis: per topic, per depth level, content coverage.

    Each entry:
    {
        'slug': ...,
        'display_name': ...,
        'depths': {'intro': [id, ...], 'intermediate': [...], 'advanced': [...]},
        'faq_gaps': ['question with no content', ...],
    }
    """
    notes = load_all_notes(vault_path)
    topics = list_topics(vault_path)

    # Build topic → notes mapping
    topic_notes: dict[str, list[dict]] = {}
    for note in notes:
        for t in (note.get("topics") or []):
            topic_notes.setdefault(t, []).append(note)

    gaps = []
    for topic in topics:
        slug = topic.get("slug", "")
        display_name = topic.get("display_name", slug)
        topic_content = topic_notes.get(slug, [])

        depths: dict[str, list[str]] = {"intro": [], "intermediate": [], "advanced": []}
        for note in topic_content:
            depth = note.get("depth", "")
            if depth in depths:
                depths[depth].append(note.get("id", "?"))

        # FAQ gaps: questions in topic hub with no linked content
        faq_gaps: list[str] = []
        for q in (topic.get("faqs") or []):
            if isinstance(q, dict):
                if not q.get("best_content"):
                    faq_gaps.append(q.get("question", str(q)))
            elif isinstance(q, str):
                faq_gaps.append(q)

        gaps.append({
            "slug": slug,
            "display_name": display_name,
            "depths": depths,
            "faq_gaps": faq_gaps,
            "total_content": len(topic_content),
        })

    return gaps
