"""Topic hub page CRUD."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sable.vault.notes import read_frontmatter, write_note, load_all_notes


def add_topic(slug: str, display_name: str, org: str, vault_path: Path) -> Path:
    """Create a topic hub page if it doesn't already exist."""
    from jinja2 import Environment, FileSystemLoader
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
    tmpl = env.get_template("topic_hub.md.j2")

    topic_path = vault_path / "topics" / f"{slug}.md"
    if topic_path.exists():
        return topic_path

    now = datetime.now(timezone.utc).isoformat()
    content = tmpl.render(
        slug=slug,
        display_name=display_name,
        org=org,
        created_at=now,
    )
    topic_path.parent.mkdir(parents=True, exist_ok=True)
    topic_path.write_text(content, encoding="utf-8")
    return topic_path


def list_topics(vault_path: Path) -> list[dict]:
    """Load all topic hub frontmatter."""
    topics_dir = vault_path / "topics"
    if not topics_dir.exists():
        return []
    results = []
    for md in topics_dir.glob("*.md"):
        if md.name.startswith("_"):
            continue
        try:
            fm = read_frontmatter(md)
            fm["_path"] = str(md)
            results.append(fm)
        except Exception:
            pass
    return results


def refresh_topics(org: str, vault_path: Path) -> None:
    """Re-derive topic→content links from content notes and update hub pages."""
    content_notes = load_all_notes(vault_path)

    # Build topic → list of content ids and topic → set of FAQs
    topic_map: dict[str, list[str]] = {}
    faq_map: dict[str, list[str]] = {}
    for note in content_notes:
        for t in (note.get("topics") or []):
            topic_map.setdefault(t, []).append(note.get("id", "?"))
            for q in (note.get("questions_answered") or []):
                if q not in faq_map.setdefault(t, []):
                    faq_map[t].append(q)

    topics_dir = vault_path / "topics"
    if not topics_dir.exists():
        return

    for md in topics_dir.glob("*.md"):
        if md.name.startswith("_"):
            continue
        try:
            from sable.vault.notes import read_note, write_note
            fm, body = read_note(md)
            slug = fm.get("slug", md.stem)
            content_ids = topic_map.get(slug, [])
            fm["content_count"] = len(content_ids)
            fm["faqs"] = faq_map.get(slug, [])
            write_note(md, fm, body)
        except Exception:
            pass
