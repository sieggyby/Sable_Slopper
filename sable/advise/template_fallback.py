"""Template-only fallback for Twitter strategy brief (no AI call)."""
from __future__ import annotations


def render_fallback(data: dict, reason: str) -> str:
    """Render a template-only brief when AI synthesis is unavailable."""
    lines = [f"> AI synthesis unavailable ({reason}).\n"]

    # Top posts by lift
    posts = sorted(data.get("posts", []), key=lambda p: p.get("lift", 0), reverse=True)[:5]
    if posts:
        lines.append("## Top Posts by Lift\n")
        for p in posts:
            lines.append(f"- [{p['content_type']}] lift={p.get('lift', 0):.2f}: {(p['text'] or '')[:100]}\n")

    # Trending topics
    topics = sorted(data.get("topics", []), key=lambda t: t.get("avg_lift", 0), reverse=True)[:5]
    if topics:
        lines.append("\n## Trending Topics\n")
        for t in topics:
            lines.append(f"- {t['term']} (lift={t.get('avg_lift', 0):.2f})\n")

    # Entity targets
    entities = data.get("entities", [])[:5]
    if entities:
        lines.append("\n## Entity Targets\n")
        for e in entities:
            twitter = next((h["handle"] for h in e.get("handles", []) if h["platform"] == "twitter"), "")
            handle_str = f" (@{twitter})" if twitter else ""
            lines.append(f"- {e['display_name']}{handle_str}: {', '.join(e.get('tags', []))}\n")

    # Community content
    content = data.get("content_items", [])[:5]
    if content:
        lines.append("\n## Community Content\n")
        for c in content:
            lines.append(f"- [{c['content_type']}] {(c['body'] or '')[:100]}\n")

    # Cap at 3000 chars
    result = "".join(lines)
    if len(result) > 3000:
        result = result[:2997] + "..."
    return result
