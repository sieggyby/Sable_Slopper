"""Posting log — record posts, sync from pulse DB."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sable.vault.notes import load_all_notes, read_note, write_note


def log_post(
    content_id: str,
    account: str,
    tweet_id: str,
    vault_path: Path,
    org: str,
) -> bool:
    """Mark a content note as posted and append to monthly posting log.

    Returns True if the note was found and updated.
    """
    note_path = _find_note_path(content_id, vault_path)
    if note_path is None:
        return False

    fm, body = read_note(note_path)

    # Add to posted_by if not already present
    posted_by = fm.get("posted_by") or []
    entry = {
        "account": account,
        "tweet_id": tweet_id,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "org": org,
    }
    # Deduplicate by tweet_id
    existing_ids = {
        (p.get("tweet_id") if isinstance(p, dict) else None)
        for p in posted_by
    }
    if tweet_id not in existing_ids:
        posted_by.append(entry)
    fm["posted_by"] = posted_by
    write_note(note_path, fm, body)

    # Append to monthly posting log
    _append_posting_log(content_id, account, tweet_id, fm.get("type", ""), vault_path, org)

    return True


def sync_from_pulse(org: str, vault_path: Path) -> list[dict]:
    """Query pulse DB for sable-tagged posts, return new entries not yet in vault.

    Returns list of dicts describing unlogged posts. Caller should confirm before logging.
    """
    try:
        from sable.pulse.db import get_conn
    except ImportError:
        return []

    vault_notes = load_all_notes(vault_path)
    # Build set of already-logged tweet IDs
    logged_tweet_ids: set[str] = set()
    for note in vault_notes:
        for entry in (note.get("posted_by") or []):
            if isinstance(entry, dict) and entry.get("tweet_id"):
                logged_tweet_ids.add(str(entry["tweet_id"]))

    conn = get_conn()
    cursor = conn.execute(
        "SELECT id, account_handle, url, sable_content_type, sable_content_path, posted_at "
        "FROM posts WHERE sable_content_type IS NOT NULL ORDER BY posted_at DESC LIMIT 200"
    )
    rows = cursor.fetchall()
    conn.close()

    unlogged = []
    for row in rows:
        post_id, handle, url, content_type, content_path, posted_at = row
        # Extract tweet ID from URL
        import re
        m = re.search(r"/status/(\d+)", str(url or ""))
        tweet_id = m.group(1) if m else str(post_id)
        if tweet_id not in logged_tweet_ids:
            unlogged.append({
                "account": handle,
                "tweet_id": tweet_id,
                "content_type": content_type,
                "content_path": content_path,
                "posted_at": posted_at,
                "url": url,
            })

    return unlogged


def _find_note_path(content_id: str, vault_path: Path) -> Path | None:
    """Find the note path for a given content ID."""
    content_dir = vault_path / "content"
    if not content_dir.exists():
        return None
    for md in content_dir.rglob("*.md"):
        if md.stem == content_id:
            return md
    return None


def _append_posting_log(
    content_id: str,
    account: str,
    tweet_id: str,
    content_type: str,
    vault_path: Path,
    org: str,
) -> None:
    """Append a row to the monthly posting log markdown file."""
    from jinja2 import Environment, FileSystemLoader

    now = datetime.now(timezone.utc)
    month_str = now.strftime("%Y-%m")
    log_path = vault_path / "posting-log" / f"{month_str}.md"

    if not log_path.exists():
        templates_dir = Path(__file__).parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        tmpl = env.get_template("posting_log.md.j2")
        content = tmpl.render(month=month_str, org=org)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(content, encoding="utf-8")

    date_str = now.strftime("%Y-%m-%d")
    row = f"| {date_str} | {account} | {content_id} | {content_type} | {tweet_id} |"

    existing = log_path.read_text(encoding="utf-8")
    log_path.write_text(existing.rstrip() + f"\n{row}\n", encoding="utf-8")
