"""Core vault indexer — scans *_meta.json and *.meta.json, creates/updates content notes."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from sable.vault.config import VaultConfig
from sable.vault.notes import (
    load_all_notes,
    load_sync_index,
    read_note,
    save_sync_index,
    write_note,
)


@dataclass
class SyncReport:
    new: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        parts = [f"new={self.new}", f"updated={self.updated}"]
        if self.errors:
            parts.append(f"errors={len(self.errors)}")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Type prefix mapping
# ---------------------------------------------------------------------------

_TYPE_PREFIX = {
    "clip": "clip",
    "meme": "meme",
    "faceswap": "faceswap",
    "explainer": "exp",
}

_TYPE_SUBDIR = {
    "clip": "clips",
    "meme": "memes",
    "faceswap": "faceswaps",
    "explainer": "explainers",
}


def scan_for_meta_files(workspace_path: Path) -> list[Path]:
    """Glob workspace for all *_meta.json and *.meta.json sidecar files.

    Returns sorted by mtime (oldest first → stable sequential ID assignment).
    """
    found: set[Path] = set()
    for p in workspace_path.rglob("*_meta.json"):
        found.add(p)
    for p in workspace_path.rglob("*.meta.json"):
        found.add(p)
    return sorted(found, key=lambda p: p.stat().st_mtime)


def _infer_type(meta: dict, meta_path: Path) -> str:
    """Infer content type from meta dict or file path."""
    if meta.get("type"):
        return meta["type"]
    tool = meta.get("source_tool", "")
    if "meme" in tool:
        return "meme"
    if "face" in tool:
        return "faceswap"
    if "explainer" in tool or "character" in tool:
        return "explainer"
    # Legacy clip files: have brainrot_energy or source+output+start
    if "brainrot_energy" in meta or ("start" in meta and "end" in meta and "source" in meta):
        return "clip"
    # Fall back on path
    path_str = str(meta_path).lower()
    if "meme" in path_str:
        return "meme"
    if "faceswap" in path_str or "face" in path_str:
        return "faceswap"
    if "explainer" in path_str:
        return "explainer"
    return "clip"


def _next_id(content_type: str, existing_notes: list[dict]) -> str:
    """Generate the next sequential ID for a content type."""
    prefix = _TYPE_PREFIX.get(content_type, content_type)
    existing_ids = {n.get("id", "") for n in existing_notes if n.get("type") == content_type}
    n = len(existing_ids) + 1
    # Find a free slot
    while True:
        candidate = f"{prefix}-{n:03d}"
        if candidate not in existing_ids:
            return candidate
        n += 1


def _build_note_frontmatter(meta: dict, content_id: str, content_type: str) -> dict:
    """Build frontmatter dict from raw meta dict."""
    output_path = meta.get("output", "")

    fm: dict = {
        "id": content_id,
        "type": content_type,
        "source_tool": meta.get("source_tool", f"sable-{content_type}"),
        "account": meta.get("account", ""),
        "output": output_path,
        "assembled_at": meta.get("assembled_at", ""),
        "meta_path": str(meta.get("_meta_path", "")),
        "topics": [],
        "questions_answered": [],
        "depth": "",
        "tone": "",
        "keywords": [],
        "enrichment_status": "pending",
        "suggested_for": [],
        "posted_by": [],
    }

    if content_type == "clip":
        fm["source"] = meta.get("source", "")
        fm["start"] = meta.get("start", 0)
        fm["end"] = meta.get("end", 0)
        fm["duration"] = meta.get("duration", 0)
        fm["caption"] = meta.get("caption", "")
        fm["brainrot_energy"] = meta.get("brainrot_energy", "")
    elif content_type == "meme":
        fm["template"] = meta.get("template", "")
        fm["topic"] = meta.get("topic", "")
        fm["texts"] = meta.get("texts", {})
    elif content_type == "faceswap":
        fm["target"] = meta.get("target", "")
        fm["strategy"] = meta.get("strategy", "")
    elif content_type == "explainer":
        fm["topic"] = meta.get("topic", "")
        fm["character_id"] = meta.get("character_id", "")
        fm["script_preview"] = (meta.get("script", "")[:200]).replace('"', "'")

    return fm


def _note_body(fm: dict) -> str:
    """Generate a simple markdown body for a content note."""
    content_type = fm.get("type", "")
    account = fm.get("account", "")

    if content_type == "clip":
        dur = fm.get("duration", 0)
        return f"**Clip** — {account} | {float(dur):.1f}s\n\nCaption: _{fm.get('caption', '')}_"
    elif content_type == "meme":
        return f"**Meme** — {account} | template: {fm.get('template', '')}\n\nTopic: _{fm.get('topic', '')}_"
    elif content_type == "faceswap":
        return f"**Faceswap** — {account} | strategy: {fm.get('strategy', '')}"
    elif content_type == "explainer":
        return f"**Explainer** — {account} | {fm.get('topic', '')}\n\n_{fm.get('script_preview', '')}_"
    return f"**{content_type}** — {account}"


def sync(
    org: str,
    vault_path: Path,
    workspace_path: Path,
    config: Optional[VaultConfig] = None,
    dry_run: bool = False,
) -> SyncReport:
    """Scan workspace for meta files and create/update vault content notes."""
    if config is None:
        from sable.vault.config import load_vault_config
        config = load_vault_config()

    report = SyncReport()
    sync_index = load_sync_index(vault_path)
    meta_files = scan_for_meta_files(workspace_path)
    existing_notes = load_all_notes(vault_path)

    new_items: list[dict] = []  # Items to enrich after initial write

    for meta_file in meta_files:
        abs_path = str(meta_file.resolve())
        try:
            raw = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception as e:
            report.errors.append(f"parse error {meta_file.name}: {e}")
            continue

        raw["_meta_path"] = abs_path

        content_type = _infer_type(raw, meta_file)
        output_str = raw.get("output", "")

        # Use output path as primary key for dedup; fall back to meta_path
        index_key = output_str or abs_path

        if index_key in sync_index:
            content_id = sync_index[index_key]
            subdir = _TYPE_SUBDIR.get(content_type, f"{content_type}s")
            note_path = vault_path / "content" / subdir / f"{content_id}.md"

            if note_path.exists():
                existing_fm, existing_body = read_note(note_path)
                # Update mutable fields but preserve enrichment
                existing_fm["assembled_at"] = raw.get("assembled_at", existing_fm.get("assembled_at", ""))
                existing_fm["output"] = output_str
                if not dry_run:
                    write_note(note_path, existing_fm, existing_body)
                report.updated += 1
                continue

        # New content — generate ID
        content_id = _next_id(content_type, existing_notes)
        sync_index[index_key] = content_id

        subdir = _TYPE_SUBDIR.get(content_type, f"{content_type}s")
        note_path = vault_path / "content" / subdir / f"{content_id}.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)

        fm = _build_note_frontmatter(raw, content_id, content_type)
        body = _note_body(fm)

        if not dry_run:
            write_note(note_path, fm, body)

        # Track for enrichment
        new_items.append(fm)
        # Also add to in-memory notes list for sequential ID generation
        existing_notes.append(fm)
        report.new += 1

    # Batch enrich new content
    if new_items and config.auto_enrich and not dry_run:
        org_topics = _get_org_topics(org)
        from sable.vault.enrich import enrich_batch
        try:
            enriched = enrich_batch(new_items, org_topics, config)
            for ef in enriched:
                content_type = ef.get("type", "clip")
                subdir = _TYPE_SUBDIR.get(content_type, f"{content_type}s")
                note_path = vault_path / "content" / subdir / f"{ef['id']}.md"
                if note_path.exists():
                    existing_fm, existing_body = read_note(note_path)
                    for key in ("topics", "questions_answered", "depth", "tone", "keywords", "enrichment_status"):
                        if key in ef:
                            existing_fm[key] = ef[key]
                    write_note(note_path, existing_fm, existing_body)
        except Exception as e:
            logger.warning("Batch enrichment failed: %s", e, exc_info=True)

    if not dry_run:
        save_sync_index(vault_path, sync_index)
        # Refresh supporting pages
        from sable.vault.topics import refresh_topics
        from sable.vault.voices import generate_voice_profiles
        from sable.vault.dashboard import regenerate_index
        try:
            refresh_topics(org, vault_path)
            generate_voice_profiles(org, vault_path)
            regenerate_index(org, vault_path)
        except Exception as e:
            logger.warning("vault sync: supporting page refresh failed (org=%s): %s", org, e, exc_info=True)

    return report


def _get_org_topics(org: str) -> list[str]:
    """Collect union of topics from all org accounts."""
    try:
        from sable.roster.manager import list_accounts
        accounts = list_accounts(org=org)
        topics: set[str] = set()
        for acc in accounts:
            for t in (acc.persona.topics or []):
                topics.add(t)
        return sorted(topics)
    except Exception as e:
        logger.debug("Could not load org topics: %s", e)
        return []
