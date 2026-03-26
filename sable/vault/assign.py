"""Content-to-account assignment and tweet bank integration."""
from __future__ import annotations

from pathlib import Path

from sable.vault.notes import read_note, write_note


def assign_content(
    content_id: str,
    account: str,
    caption: str | None,
    vault_path: Path,
) -> bool:
    """Assign content to an account queue.

    - Adds account to suggested_for in the content note.
    - If caption provided, appends to account's tweet_bank.

    Returns True if note was found.
    """
    note_path = _find_note_path(content_id, vault_path)
    if note_path is None:
        return False

    fm, body = read_note(note_path)

    # Add to suggested_for
    suggested_for = fm.get("suggested_for") or []
    if account not in suggested_for:
        suggested_for.append(account)
    fm["suggested_for"] = suggested_for
    write_note(note_path, fm, body)

    # Append caption to tweet bank if provided
    if caption:
        try:
            from sable.roster.manager import append_tweet
            append_tweet(account, caption)
        except Exception:
            pass

    return True


def _find_note_path(content_id: str, vault_path: Path) -> Path | None:
    content_dir = vault_path / "content"
    if not content_dir.exists():
        return None
    for md in content_dir.rglob("*.md"):
        if md.stem == content_id:
            return md
    return None
