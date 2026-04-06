"""Clip review — triage queue for unreviewed clips."""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from sable.shared.files import atomic_write

logger = logging.getLogger(__name__)


@dataclass
class ClipCandidate:
    """A clip awaiting review."""

    clip_path: Path
    meta_path: Path
    meta: dict
    duration: float
    transcript_excerpt: str
    selection_score: float | None


def find_unreviewed_clips(org: str) -> list[ClipCandidate]:
    """Find clips with .meta.json but no vault_note_id."""
    from sable.roster.manager import list_accounts
    from sable.shared.paths import workspace

    accounts = list_accounts(org=org, active_only=True)
    ws = workspace()
    candidates: list[ClipCandidate] = []

    for acc in accounts:
        output_dir = ws / "output" / acc.handle
        if not output_dir.exists():
            continue

        for meta_path in sorted(output_dir.rglob("*.meta.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Skipping unreadable meta: %s", meta_path)
                continue

            if meta.get("vault_note_id"):
                continue

            # Derive clip path: foo.meta.json → foo.mp4
            clip_path = meta_path.with_suffix("").with_suffix(".mp4")

            duration = meta.get("duration", 0.0)
            caption = meta.get("caption", "")
            words = caption.split()[:50]
            excerpt = " ".join(words)
            if len(caption.split()) > 50:
                excerpt += "..."

            score = meta.get("score")
            if score is not None:
                try:
                    score = float(score)
                except (TypeError, ValueError):
                    score = None

            candidates.append(ClipCandidate(
                clip_path=clip_path,
                meta_path=meta_path,
                meta=meta,
                duration=duration,
                transcript_excerpt=excerpt,
                selection_score=score,
            ))

    return candidates


def approve_clip(candidate: ClipCandidate, vault_note_id: str) -> None:
    """Stamp vault_note_id into the clip's meta.json."""
    candidate.meta["vault_note_id"] = vault_note_id
    atomic_write(candidate.meta_path, json.dumps(candidate.meta, indent=2))


def reject_clip(candidate: ClipCandidate) -> None:
    """Move clip + meta to a _rejected/ subdirectory."""
    rejected_dir = candidate.meta_path.parent / "_rejected"
    rejected_dir.mkdir(parents=True, exist_ok=True)

    # Move meta
    dest_meta = rejected_dir / candidate.meta_path.name
    shutil.move(str(candidate.meta_path), str(dest_meta))

    # Move clip if it exists
    if candidate.clip_path.exists():
        dest_clip = rejected_dir / candidate.clip_path.name
        shutil.move(str(candidate.clip_path), str(dest_clip))

    # Move thumbnail if it exists
    thumb = candidate.clip_path.with_suffix(".thumbnail.png")
    if thumb.exists():
        shutil.move(str(thumb), str(rejected_dir / thumb.name))
