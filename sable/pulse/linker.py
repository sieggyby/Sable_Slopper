"""Auto-link tweets to sable content via caption similarity."""
from __future__ import annotations

from typing import Optional

from sable.pulse.db import get_conn


def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance."""
    try:
        from Levenshtein import distance
        return distance(a, b)
    except ImportError:
        # Fallback pure Python
        if len(a) < len(b):
            return _levenshtein(b, a)
        if not a:
            return len(b)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
            prev = curr
        return prev[-1]


def similarity_ratio(a: str, b: str) -> float:
    """Return similarity 0-100 between two strings."""
    if not a and not b:
        return 100.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 100.0
    dist = _levenshtein(a.lower(), b.lower())
    return round((1 - dist / max_len) * 100, 1)


def auto_link_posts(threshold: float = 70.0) -> list[dict]:
    """
    Find unlinked posts and attempt to match them to sable content
    using caption similarity.
    Returns list of {post_id, matched_path, similarity} dicts.
    """
    conn = get_conn()
    unlinked = conn.execute(
        "SELECT id, text FROM posts WHERE sable_content_path = '' OR sable_content_path IS NULL"
    ).fetchall()

    # Get all known captions from meme/clip outputs (would be tracked in production)
    # For now, return empty — manual linking is the primary path
    conn.close()
    return []


def manual_link(post_id: str, content_type: str, content_path: str) -> None:
    """Manually link a tweet to a sable content item."""
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE posts SET sable_content_type = ?, sable_content_path = ? WHERE id = ?",
            (content_type, content_path, post_id),
        )
    conn.close()
