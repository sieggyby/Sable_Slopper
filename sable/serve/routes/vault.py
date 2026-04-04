"""Vault API routes — content inventory and search."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Query

from sable.serve.deps import get_pulse_db, resolve_vault_path
from sable.vault.notes import load_all_notes
from sable.roster.manager import list_accounts

router = APIRouter()

_STALE_DAYS = 14


def _age_days(produced_at: str | None) -> int:
    if not produced_at:
        return 0
    try:
        dt = datetime.fromisoformat(produced_at[:19])
        return (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)).days
    except (ValueError, TypeError):
        return 0


@router.get("/inventory/{org}")
def vault_inventory(org: str):
    """Vault content inventory — total produced, posted, unused, by-format breakdown."""
    try:
        vault_path = resolve_vault_path(org)
    except Exception:
        return {"error": "Invalid org", "org": org}

    notes = load_all_notes(vault_path)

    # Cross-reference with pulse.db for posted status
    pulse = get_pulse_db()
    accounts = list_accounts(org=org)
    handles = {a.handle for a in accounts}

    # Build set of posted vault note paths from pulse
    posted_paths: set[str] = set()
    if handles:
        placeholders = ",".join("?" for _ in handles)
        rows = pulse.execute(
            f"""SELECT sable_content_path FROM posts
                WHERE account_handle IN ({placeholders})
                  AND sable_content_path IS NOT NULL AND sable_content_path != ''""",
            tuple(handles),
        ).fetchall()
        posted_paths = {r["sable_content_path"] for r in rows}

    # Also check posted_by frontmatter field
    posted_notes = []
    posted_note_paths: set[str] = set()
    unused_notes = []
    for note in notes:
        note_path = note.get("_note_path", "")
        posted_by = note.get("posted_by") or []
        is_posted = (
            note_path in posted_paths
            or any(
                (h if isinstance(h, str) else h.get("account", "")) in handles
                for h in posted_by
            )
        )
        if is_posted:
            posted_notes.append(note)
            posted_note_paths.add(note_path)
        else:
            unused_notes.append(note)

    # By-format breakdown
    by_format: dict[str, dict] = {}
    for note in notes:
        fmt = note.get("type") or note.get("format") or "unknown"
        bucket = by_format.setdefault(fmt, {"format": fmt, "produced": 0, "posted": 0, "unused": 0})
        bucket["produced"] += 1
        if note.get("_note_path", "") in posted_note_paths:
            bucket["posted"] += 1
        else:
            bucket["unused"] += 1

    # Get performance for recent posted notes
    recent_posted = []
    for note in posted_notes[:20]:
        note_path = note.get("_note_path", "")
        # Try to find matching post in pulse
        post_row = None
        if note_path:
            post_row = pulse.execute(
                "SELECT id, posted_at FROM posts WHERE sable_content_path = ? LIMIT 1",
                (note_path,),
            ).fetchone()

        perf = {}
        if post_row:
            snap = pulse.execute(
                """SELECT likes, retweets, replies, views, bookmarks, quotes
                   FROM snapshots WHERE post_id = ?
                   ORDER BY taken_at DESC LIMIT 1""",
                (post_row["id"],),
            ).fetchone()
            if snap:
                eng = (
                    (snap["likes"] or 0) + (snap["retweets"] or 0) + (snap["replies"] or 0)
                    + (snap["quotes"] or 0) + (snap["bookmarks"] or 0)
                )
                perf = {"engagement": eng}

        recent_posted.append({
            "title": note.get("topic") or note.get("caption") or note.get("id", ""),
            "format": note.get("type") or note.get("format") or "unknown",
            "produced_at": note.get("created_at") or note.get("produced_at") or "",
            "posted_at": dict(post_row).get("posted_at", "") if post_row else "",
            "performance": perf,
        })

    # Unused assets
    unused_assets = []
    for note in unused_notes:
        produced = note.get("created_at") or note.get("produced_at") or ""
        unused_assets.append({
            "title": note.get("topic") or note.get("caption") or note.get("id", ""),
            "format": note.get("type") or note.get("format") or "unknown",
            "produced_at": produced,
            "age_days": _age_days(produced),
        })
    unused_assets.sort(key=lambda x: x["age_days"], reverse=True)

    return {
        "total_produced": len(notes),
        "total_posted": len(posted_notes),
        "total_unused": len(unused_notes),
        "stale_threshold_days": _STALE_DAYS,
        "by_format": list(by_format.values()),
        "unused_assets": unused_assets[:50],
        "recent_posted": recent_posted,
    }


@router.get("/search/{org}")
def vault_search(
    org: str,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
):
    """Search vault content notes by keyword matching."""
    try:
        vault_path = resolve_vault_path(org)
    except Exception:
        return []

    notes = load_all_notes(vault_path)
    if not notes:
        return []

    # Keyword prescore (no Claude call — this is a read-only API, no spend)
    query_tokens = set(q.lower().split())
    scored = []
    for note in notes:
        text_fields = [
            note.get("topic", ""),
            note.get("caption", ""),
            " ".join(note.get("keywords", [])),
            " ".join(note.get("questions_answered", [])),
            note.get("script_preview", ""),
            note.get("depth", ""),
            note.get("tone", ""),
        ]
        combined = " ".join(str(f) for f in text_fields).lower()
        score = sum(1 for t in query_tokens if t in combined)
        if score > 0:
            scored.append((note, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    for note, score in scored[:limit]:
        results.append({
            "title": note.get("topic") or note.get("caption") or note.get("id", ""),
            "path": note.get("_note_path", ""),
            "score": score,
            "format": note.get("type") or note.get("format") or "unknown",
            "frontmatter": {
                k: v for k, v in note.items()
                if k != "_note_path" and not k.startswith("_")
            },
        })

    return results
