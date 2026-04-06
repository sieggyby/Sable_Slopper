"""Client handoff zip export."""
from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sable.vault.notes import load_all_notes, read_note, write_note

logger = logging.getLogger(__name__)


_STRIP_FM_KEYS = {"meta_path", "media_path"}
_STRIP_DIRS = {".obsidian", "_sable-internal"}


def export_vault(
    org: str,
    vault_path: Path,
    output_path: Path,
    include_media: bool = False,
) -> Path:
    """Export org vault to a client-ready zip.

    - Strips .obsidian/, _sable-internal/
    - Strips meta_path / media_path from frontmatter
    - Optionally copies media files
    - Generates README.md
    - Returns path to zip file
    """
    skipped: list[str] = []

    with tempfile.TemporaryDirectory(prefix="sable_export_") as tmp:
        tmp_path = Path(tmp) / org
        tmp_path.mkdir(parents=True)

        # Copy vault files
        for item in vault_path.iterdir():
            if item.name in _STRIP_DIRS:
                continue
            if item.name.startswith("."):
                continue
            if item.is_dir():
                shutil.copytree(str(item), str(tmp_path / item.name))
            else:
                shutil.copy2(str(item), str(tmp_path / item.name))

        # Strip sensitive frontmatter keys from all .md files
        for md_file in tmp_path.rglob("*.md"):
            try:
                fm, body = read_note(md_file)
                changed = False
                for key in _STRIP_FM_KEYS:
                    if key in fm:
                        del fm[key]
                        changed = True
                if changed:
                    write_note(md_file, fm, body)
            except Exception as e:
                logger.warning("Failed to strip frontmatter from %s: %s", md_file, e)

        # Optionally copy media files
        if include_media:
            notes = load_all_notes(vault_path)
            media_dir = tmp_path / "media"
            media_dir.mkdir(exist_ok=True)
            for note in notes:
                out = note.get("output", "")
                if out:
                    src = Path(out)
                    if src.exists():
                        shutil.copy2(str(src), str(media_dir / src.name))
                    else:
                        skipped.append(out)

        # Generate README.md
        _write_readme(org, tmp_path, vault_path, include_media)

        # Zip
        output_path.parent.mkdir(parents=True, exist_ok=True)
        zip_base = str(output_path.with_suffix(""))
        shutil.make_archive(zip_base, "zip", str(tmp_path.parent), org)

    if skipped:
        print(f"  Skipped {len(skipped)} missing media files")

    return output_path if output_path.suffix == ".zip" else Path(zip_base + ".zip")


def _write_readme(org: str, tmp_path: Path, vault_path: Path, include_media: bool) -> None:
    """Generate README.md in export root."""
    from jinja2 import Environment, FileSystemLoader

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
    tmpl = env.get_template("handoff_readme.md.j2")

    notes = load_all_notes(vault_path)
    counts = {"clip": 0, "meme": 0, "faceswap": 0, "explainer": 0}
    posted = 0
    for n in notes:
        t = n.get("type", "")
        if t in counts:
            counts[t] += 1
        if n.get("posted_by"):
            posted += 1

    total = sum(counts.values())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    content = tmpl.render(
        org=org,
        exported_at=now,
        total_clips=counts["clip"],
        total_memes=counts["meme"],
        total_faceswaps=counts["faceswap"],
        total_explainers=counts["explainer"],
        total_content=total,
        total_posted=posted,
        total_available=total - posted,
    )

    (tmp_path / "README.md").write_text(content, encoding="utf-8")
