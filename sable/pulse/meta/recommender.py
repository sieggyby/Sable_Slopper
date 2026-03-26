"""Vault integration + three-pane recommendations."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from sable.pulse.meta.trends import TrendResult
from sable.pulse.meta.fingerprint import FORMAT_BUCKETS


# ---------------------------------------------------------------------------
# Recommendation archetypes (display layer ONLY — never used in trend math)
# ---------------------------------------------------------------------------

RECOMMENDATION_ARCHETYPES: dict[str, dict] = {
    "explainer_clip": {
        "bucket": "short_clip",
        "attributes": ["explanatory"],
        "description": "Educational short video — concept breakdown, how-it-works",
    },
    "reaction_clip": {
        "bucket": "short_clip",
        "attributes": ["confrontational", "reactive"],
        "description": "Hot take or reaction over video footage",
    },
    "face_clip": {
        "bucket": "short_clip",
        "attributes": ["has_face"],
        "description": "Talking-head or face-led short video",
    },
    "meme": {
        "bucket": "single_image",
        "attributes": ["meme_humor"],
        "description": "Template meme or humor image",
    },
    "data_visual": {
        "bucket": "single_image",
        "attributes": ["technical"],
        "description": "Chart, infographic, or data screenshot",
    },
    "screenshot_receipt": {
        "bucket": "single_image",
        "attributes": ["confrontational", "reactive"],
        "description": "Screenshot of another tweet/article with commentary",
    },
    "sharp_qt": {
        "bucket": "quote_tweet",
        "attributes": ["confrontational", "short_text"],
        "description": "Short, punchy quote tweet — dunk or one-liner",
    },
    "additive_qt": {
        "bucket": "quote_tweet",
        "attributes": ["explanatory"],
        "description": "Quote tweet adding context, analysis, or nuance",
    },
    "one_liner": {
        "bucket": "standalone_text",
        "attributes": ["short_text"],
        "description": "Short declarative text tweet — aphorism, hot take",
    },
    "mini_essay": {
        "bucket": "standalone_text",
        "attributes": [],
        "description": "Longer single-tweet text — opinion, analysis",
    },
    "thread_with_hook": {
        "bucket": "thread",
        "attributes": ["original"],
        "description": "Multi-tweet thread with strong opening hook",
    },
}

# Sable content types that map to format buckets
_FORMAT_TO_CONTENT_TYPES: dict[str, list[str]] = {
    "short_clip": ["clip", "explainer"],
    "long_clip": ["clip"],
    "single_image": ["meme", "faceswap"],
    "quote_tweet": ["text_tweet"],
    "standalone_text": ["text_tweet"],
    "thread": ["text_tweet"],
    "link_share": [],
    "mixed_media": ["clip", "meme"],
}


def assign_archetype(format_bucket: str, attributes: list[str]) -> str:
    """Best-match archetype for a bucket + attribute combination.

    Archetypes are a display layer only — never used in trend math.
    """
    best_match = None
    best_score = -1

    for name, arch in RECOMMENDATION_ARCHETYPES.items():
        if arch["bucket"] != format_bucket:
            continue
        overlap = len(set(arch["attributes"]) & set(attributes))
        if overlap > best_score:
            best_score = overlap
            best_match = name

    return best_match or format_bucket


# ---------------------------------------------------------------------------
# Priority scoring
# ---------------------------------------------------------------------------

@dataclass
class PostNowRecommendation:
    content_id: str
    title: str
    file_path: str
    account: str
    format_bucket: str
    archetype: str
    priority_score: float
    confidence: str
    reason: str             # surfaces top 2-3 numeric drivers
    urgency: str            # "high" | "medium" | "low"
    effort: str             # "low" | "medium" | "high"
    shelf_life: str         # "hours" | "days" | "weeks"


def compute_priority(
    trend: TrendResult,
    content: dict,
    account_handle: str,
    vault_path: Optional[Path],
    days_idle: int = 0,
    org: str = "",
) -> tuple[float, str]:
    """Compute priority score and human-readable breakdown.

    Returns (score, reason_string).
    """
    # Trend strength (0-40 points)
    lift = trend.current_lift or 0.0
    trend_score = min(lift * 10, 40)

    # Confidence (0-30 points)
    confidence_score = {"A": 30, "B": 20, "C": 5}.get(trend.confidence, 0)

    # Account fit (0-15 points) — simplified: 8 pts base, can be upgraded via learned prefs
    fit_score = 8  # default; would be 15 if content type in learned_preferences

    # Asset freshness (0-10 points)
    posted_by = content.get("posted_by", [])
    times_posted = len(posted_by) if isinstance(posted_by, list) else 0
    freshness_score = max(10 - (times_posted * 4), 0)

    # Inventory fatigue penalty (-5 to 0)
    same_org_posts = len([p for p in posted_by if isinstance(p, dict) and p.get("org") == org])
    fatigue_penalty = max(min(same_org_posts * -2, 0), -5)

    # Similar recent post penalty
    if vault_path and has_similar_recent_post(account_handle, content, vault_path, days=7):
        fatigue_penalty = max(fatigue_penalty - 3, -5)

    # Account urgency (0-5 points)
    urgency_score = min(days_idle, 5)

    total = trend_score + confidence_score + fit_score + freshness_score + fatigue_penalty + urgency_score

    # Build reason showing top 2-3 numeric drivers
    components = [
        ("trend strength", trend_score),
        (f"confidence {trend.confidence}", confidence_score),
        ("freshness" if freshness_score > 0 else "posted before", freshness_score),
        (f"account idle {days_idle}d", urgency_score),
        ("account fit", fit_score),
    ]
    if fatigue_penalty < 0:
        components.append(("fatigue", fatigue_penalty))

    # Sort by abs value, take top 3
    components.sort(key=lambda c: abs(c[1]), reverse=True)
    top_parts = " + ".join(
        f"{name} ({val:+.0f})" if val < 0 else f"{name} ({val:.0f})"
        for name, val in components[:3]
    )
    if fatigue_penalty < 0 and ("fatigue", fatigue_penalty) not in components[:3]:
        top_parts += f" - fatigue ({fatigue_penalty:.0f})"

    reason = f"Priority {total:.0f}: {top_parts}"

    return total, reason


def has_similar_recent_post(
    account_handle: str,
    content: dict,
    vault_path: Path,
    days: int = 7,
) -> bool:
    """Check if account posted similar content (same topic + format) recently."""
    try:
        from sable.vault.notes import load_all_notes
        notes = load_all_notes(vault_path)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        content_type = content.get("type", "")
        content_topics = set(content.get("topics", []))

        for note in notes:
            posted_by = note.get("posted_by", [])
            if not isinstance(posted_by, list):
                continue
            for post in posted_by:
                if not isinstance(post, dict):
                    continue
                if post.get("account") != account_handle:
                    continue
                post_date = post.get("posted_at", "")
                if post_date < cutoff:
                    continue
                # Same content type and overlapping topics
                if note.get("type") == content_type:
                    note_topics = set(note.get("topics", []))
                    if content_topics & note_topics:
                        return True
    except Exception:
        pass
    return False


def get_days_since_last_post(account_handle: str, vault_path: Path) -> int:
    """Get days since account's last posted content (from vault)."""
    try:
        from sable.vault.notes import load_all_notes
        notes = load_all_notes(vault_path)
        latest = None
        for note in notes:
            posted_by = note.get("posted_by", [])
            if not isinstance(posted_by, list):
                continue
            for post in posted_by:
                if not isinstance(post, dict):
                    continue
                if post.get("account") != account_handle:
                    continue
                d = post.get("posted_at", "")
                if d and (latest is None or d > latest):
                    latest = d
        if latest:
            try:
                dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - dt
                return max(int(delta.days), 0)
            except Exception:
                pass
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# Three-pane generation
# ---------------------------------------------------------------------------

def build_recommendations(
    trends: dict[str, TrendResult],
    accounts: list,
    vault_path: Optional[Path],
    analysis: dict,
    cfg: dict | None = None,
    org: str = "",
) -> dict:
    """Build all three recommendation panes.

    Returns:
    {
        "post_now": [PostNowRecommendation, ...],
        "stop_doing": [{"format": str, "evidence": str, "confidence": str}],
        "gaps_to_fill": [{"format": str, "content_type": str, "lift": float, "urgency": str}],
    }
    """
    cfg = cfg or {}

    post_now: list[PostNowRecommendation] = []
    stop_doing: list[dict] = []
    gaps_to_fill: list[dict] = []

    # Load vault content if available
    vault_notes: list[dict] = []
    if vault_path and vault_path.exists():
        try:
            from sable.vault.notes import load_all_notes
            vault_notes = load_all_notes(vault_path)
        except Exception:
            vault_notes = []

    for bucket, trend in trends.items():
        # Stop Doing: declining/dead formats with A or B confidence
        if trend.trend_status in ("declining", "dead") and trend.confidence in ("A", "B"):
            evidence = (
                f"{trend.current_lift:.2f}x lift vs "
                f"{trend.lift_vs_30d:.2f}x 30d baseline — "
                f"{trend.trend_status}"
            )
            stop_doing.append({
                "format": bucket,
                "evidence": evidence,
                "confidence": trend.confidence,
                "confidence_reasons": trend.confidence_reasons,
            })

        # Post Now + Gaps: surging/rising with A or B confidence
        elif trend.trend_status in ("surging", "rising") and trend.confidence in ("A", "B"):
            matching_types = _FORMAT_TO_CONTENT_TYPES.get(bucket, [])
            matching_content = [
                n for n in vault_notes
                if n.get("type") in matching_types
            ]

            if not matching_content:
                # Gap to fill
                urgency = "high" if trend.trend_status == "surging" else "medium"
                effort = "high" if bucket in ("short_clip", "long_clip") else "medium"
                produce_type = matching_types[0] if matching_types else "content"
                gaps_to_fill.append({
                    "format": bucket,
                    "content_type": produce_type,
                    "lift": trend.current_lift,
                    "trend_status": trend.trend_status,
                    "confidence": trend.confidence,
                    "urgency": urgency,
                    "effort": effort,
                })
            else:
                # Build Post Now recommendations
                for content in matching_content:
                    for account in accounts:
                        acc_handle = getattr(account, "handle", str(account))
                        days_idle = get_days_since_last_post(acc_handle, vault_path) if vault_path else 0

                        score, reason = compute_priority(
                            trend=trend,
                            content=content,
                            account_handle=acc_handle,
                            vault_path=vault_path,
                            days_idle=days_idle,
                            org=org,
                        )

                        attrs = analysis.get("dominant_format_attrs", [])
                        archetype = assign_archetype(bucket, attrs)

                        urgency = "high" if trend.trend_status == "surging" else "medium"
                        effort = "high" if bucket in ("short_clip", "long_clip") else "low"
                        shelf_life = "hours" if trend.momentum == "decelerating" else "days"

                        post_now.append(PostNowRecommendation(
                            content_id=content.get("id", content.get("_note_path", "unknown")),
                            title=content.get("title", "Untitled"),
                            file_path=content.get("_note_path", ""),
                            account=acc_handle,
                            format_bucket=bucket,
                            archetype=archetype,
                            priority_score=score,
                            confidence=trend.confidence,
                            reason=reason,
                            urgency=urgency,
                            effort=effort,
                            shelf_life=shelf_life,
                        ))

    # Sort Post Now by priority descending
    post_now.sort(key=lambda r: r.priority_score, reverse=True)

    return {
        "post_now": post_now,
        "stop_doing": stop_doing,
        "gaps_to_fill": gaps_to_fill,
    }
