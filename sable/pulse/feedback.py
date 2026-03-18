"""Write learned_preferences back to roster.yaml from pulse data."""
from __future__ import annotations

from sable.pulse.db import get_posts_for_account, get_latest_snapshot
from sable.pulse.scorer import score_post, rank_posts
from sable.roster.manager import update_learned_preferences


def update_preferences_from_performance(handle: str, followers: int = 1000) -> dict:
    """
    Analyze performance data and write learned_preferences to roster.
    Called after recommend to close the loop.
    """
    posts = get_posts_for_account(handle, limit=200)
    scored = []
    for post in posts:
        snap = get_latest_snapshot(post["id"])
        if not snap:
            continue
        s = score_post(snap, followers=followers)
        s["content_type"] = post.get("sable_content_type", "unknown")
        s["text"] = post.get("text", "")
        scored.append(s)

    if not scored:
        return {}

    # Group by content type
    by_type: dict[str, list] = {}
    for s in scored:
        ct = s["content_type"]
        by_type.setdefault(ct, []).append(s)

    prefs = {}

    # Best performing content type
    type_er = {ct: sum(s["engagement_rate"] for s in ss) / len(ss)
               for ct, ss in by_type.items()}
    if type_er:
        best_type = max(type_er, key=type_er.get)
        prefs["best_content_type"] = best_type
        prefs["best_content_type_avg_er"] = round(type_er[best_type], 3)

    # Top performing post topics (first 5 words of top posts)
    ranked = rank_posts(scored)
    top_texts = [p["text"][:60] for p in ranked[:5]]
    if top_texts:
        prefs["top_performing_posts_preview"] = top_texts

    # Average engagement rate
    avg_er = sum(s["engagement_rate"] for s in scored) / len(scored)
    prefs["avg_engagement_rate"] = round(avg_er, 3)
    prefs["posts_analyzed"] = len(scored)

    update_learned_preferences(handle, prefs)
    return prefs
