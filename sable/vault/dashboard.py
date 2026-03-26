"""_index.md generation for vault dashboard."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sable.vault.notes import load_all_notes


def regenerate_index(org: str, vault_path: Path) -> None:
    """Rewrite _index.md with current vault statistics."""
    from jinja2 import Environment, FileSystemLoader

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
    tmpl = env.get_template("index.md.j2")

    notes = load_all_notes(vault_path)

    counts = {"clip": 0, "meme": 0, "faceswap": 0, "explainer": 0}
    for n in notes:
        t = n.get("type", "")
        if t in counts:
            counts[t] += 1

    # Per-account stats
    acc_map: dict[str, dict] = {}
    for n in notes:
        handle = n.get("account", "")
        if not handle:
            continue
        if handle not in acc_map:
            acc_map[handle] = {"handle": handle, "content_count": 0, "posted_count": 0}
        acc_map[handle]["content_count"] += 1
        if n.get("posted_by"):
            acc_map[handle]["posted_count"] += 1

    # Top unused content (no posted_by entries)
    unused = [
        n for n in notes
        if not n.get("posted_by")
    ][:10]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    content = tmpl.render(
        org=org,
        generated_at=now,
        total_clips=counts["clip"],
        total_memes=counts["meme"],
        total_faceswaps=counts["faceswap"],
        total_explainers=counts["explainer"],
        total_content=sum(counts.values()),
        accounts=sorted(acc_map.values(), key=lambda x: x["handle"]),
        top_unused=unused,
    )

    index_path = vault_path / "_index.md"
    index_path.write_text(content, encoding="utf-8")
