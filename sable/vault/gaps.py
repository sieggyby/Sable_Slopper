"""Coverage gap analysis per topic."""
from __future__ import annotations

from pathlib import Path

from sable.vault.notes import load_all_notes
from sable.vault.topics import list_topics


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
