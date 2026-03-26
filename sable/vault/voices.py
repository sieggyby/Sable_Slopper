"""Voice profile page generation from org roster."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def generate_voice_profiles(org: str, vault_path: Path) -> None:
    """Write voices/{handle_slug}.md for each account in org."""
    from jinja2 import Environment, FileSystemLoader
    from sable.roster.manager import list_accounts
    from sable.vault.notes import load_all_notes

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
    tmpl = env.get_template("voice_profile.md.j2")

    accounts = list_accounts(org=org)
    now = datetime.now(timezone.utc).isoformat()

    # Count content per account from existing notes
    content_notes = load_all_notes(vault_path)
    content_by_account: dict[str, int] = {}
    posted_by_account: dict[str, int] = {}
    for note in content_notes:
        handle = note.get("account", "")
        content_by_account[handle] = content_by_account.get(handle, 0) + 1
        for entry in (note.get("posted_by") or []):
            acc = entry if isinstance(entry, str) else entry.get("account", "")
            posted_by_account[acc] = posted_by_account.get(acc, 0) + 1

    voices_dir = vault_path / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)

    for acc in accounts:
        slug = acc.handle.lstrip("@")
        profile_path = voices_dir / f"{slug}.md"

        content = tmpl.render(
            handle=acc.handle,
            display_name=acc.display_name or acc.handle,
            org=org,
            archetype=acc.persona.archetype or "",
            voice=acc.persona.voice or "",
            topics=acc.persona.topics or [],
            avoid=acc.persona.avoid or [],
            clip_style=acc.content.clip_style or "standard",
            meme_style=acc.content.meme_style or "classic",
            brainrot_energy=acc.content.brainrot_energy or "medium",
            created_at=now,
        )

        # Compute avg_engagement from pulse DB
        avg_engagement = 0.0
        try:
            from sable.pulse.db import get_posts_for_account, get_latest_snapshot
            posts = get_posts_for_account(acc.handle)
            totals = []
            for post in posts:
                snap = get_latest_snapshot(post["id"])
                if snap:
                    totals.append(
                        snap.get("likes", 0) + snap.get("retweets", 0)
                        + snap.get("replies", 0) + snap.get("quotes", 0)
                        + snap.get("bookmarks", 0)
                    )
            if totals:
                avg_engagement = sum(totals) / len(totals)
        except Exception:
            pass

        # If profile exists, preserve existing content counts
        if profile_path.exists():
            from sable.vault.notes import read_note, write_note
            existing_fm, existing_body = read_note(profile_path)
            existing_fm["content_count"] = content_by_account.get(acc.handle, 0)
            existing_fm["posted_count"] = posted_by_account.get(acc.handle, 0)
            existing_fm["avg_engagement"] = round(avg_engagement, 2)
            existing_fm["last_updated"] = now
            write_note(profile_path, existing_fm, existing_body)
        else:
            profile_path.write_text(content, encoding="utf-8")
