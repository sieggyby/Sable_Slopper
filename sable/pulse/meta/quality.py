"""Engagement quality scoring, confidence grading, and aggregation entry point."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sable.pulse.meta.normalize import AuthorNormalizedTweet, weighted_mean_lift, MAX_LIFT


@dataclass
class EngagementQuality:
    confidence: str             # "A" | "B" | "C"
    confidence_reasons: list[str]
    sample_count: int
    unique_authors: int
    concentration: float        # fraction of signal from top 2 authors
    all_fallback: bool          # True if every tweet is from fallback-quality authors
    mixed_quality_warning: str  # non-empty if fallback vs strong authors disagree significantly


def assess_format_quality(tweets: list[AuthorNormalizedTweet]) -> EngagementQuality:
    """Grade the confidence of a format bucket's engagement signal.

    Grades:
    - A: strong sample, diverse authors, good history
    - B: adequate signal, directional
    - C: weak, anecdotal

    Hard rule: if all tweets are from fallback authors → max grade B.
    """
    reasons: list[str] = []

    n = len(tweets)
    if n == 0:
        return EngagementQuality(
            confidence="C",
            confidence_reasons=["no tweets in bucket"],
            sample_count=0,
            unique_authors=0,
            concentration=0.0,
            all_fallback=True,
            mixed_quality_warning="",
        )

    unique_authors = len({t.author_handle for t in tweets})

    # --- Sample count score ---
    if n >= 15:
        sample_score = 2  # strong
    elif n >= 8:
        sample_score = 1  # adequate
    elif n >= 4:
        sample_score = 0  # weak
    else:
        reasons.append(f"insufficient sample ({n} tweets, need 4+)")
        return EngagementQuality(
            confidence="C",
            confidence_reasons=reasons,
            sample_count=n,
            unique_authors=unique_authors,
            concentration=0.0,
            all_fallback=False,
            mixed_quality_warning="",
        )

    # --- Author diversity score ---
    if unique_authors >= 8:
        author_score = 2  # strong
    elif unique_authors >= 4:
        author_score = 1  # adequate
    elif unique_authors >= 2:
        author_score = 0  # weak
        reasons.append(f"limited author diversity ({unique_authors} unique authors)")
    else:
        reasons.append("single author — unreliable signal")
        return EngagementQuality(
            confidence="C",
            confidence_reasons=reasons,
            sample_count=n,
            unique_authors=unique_authors,
            concentration=1.0,
            all_fallback=False,
            mixed_quality_warning="",
        )

    # --- Concentration check ---
    # Fraction of total lift from top 2 authors
    author_lift: dict[str, float] = {}
    for t in tweets:
        if t.total_lift is None:
            continue
        author_lift[t.author_handle] = author_lift.get(t.author_handle, 0.0) + t.total_lift

    total_lift_sum = sum(author_lift.values())
    sorted_authors = sorted(author_lift.values(), reverse=True)
    top2_lift = sum(sorted_authors[:2])
    concentration = top2_lift / total_lift_sum if total_lift_sum > 0 else 0.0
    concentrated = concentration > 0.50
    if concentrated:
        reasons.append(f"concentrated signal (top 2 authors = {concentration:.0%} of lift)")

    # --- Author history quality ---
    all_fallback = all(t.author_quality.grade == "fallback" for t in tweets)
    if all_fallback:
        reasons.append("all contributing authors have fallback-quality history")

    # --- Mixed quality contradiction check ---
    mixed_quality_warning = ""
    fallback_tweets = [t for t in tweets if t.author_quality.grade == "fallback"]
    strong_tweets = [t for t in tweets if t.author_quality.grade in ("strong", "adequate")]
    fallback_lifts = [t.total_lift for t in fallback_tweets if t.total_lift is not None]
    strong_lifts = [t.total_lift for t in strong_tweets if t.total_lift is not None]
    if fallback_lifts and strong_lifts:
        fb_avg = sum(fallback_lifts) / len(fallback_lifts)
        st_avg = sum(strong_lifts) / len(strong_lifts)
        # If fallback authors show significantly higher lift than strong authors, flag it
        if fb_avg > st_avg * 2.0 and fb_avg > 2.0:
            mixed_quality_warning = (
                f"Trend signal is mostly driven by authors with limited history — "
                f"strong-history authors show near-baseline engagement for this format "
                f"(fallback avg lift {fb_avg:.1f}x vs strong-history avg {st_avg:.1f}x)."
            )
            reasons.append("fallback authors showing higher lift than strong-history authors")

    # --- Variance warning for small buckets ---
    if n <= 6:
        lifts = [t.total_lift for t in tweets if t.total_lift is not None]
        if len(lifts) >= 2:
            max_lift = max(lifts)
            min_lift = min(lifts)
            if max_lift > 5.0 and (max_lift - min_lift) > 4.0:
                reasons.append(f"high variance in small bucket (range {min_lift:.1f}x–{max_lift:.1f}x)")

    # --- Compute grade ---
    total_score = sample_score + author_score
    if concentrated:
        total_score -= 1
    if all_fallback:
        total_score -= 1

    if total_score >= 4:
        grade = "A"
    elif total_score >= 2:
        grade = "B"
    else:
        grade = "C"

    # Hard cap: fallback authors → max B
    if all_fallback and grade == "A":
        grade = "B"
        reasons.append("capped at B: all authors have fallback-quality history")

    if not reasons:
        reasons.append("sufficient sample, diverse authors, good history")

    return EngagementQuality(
        confidence=grade,
        confidence_reasons=reasons,
        sample_count=n,
        unique_authors=unique_authors,
        concentration=concentration,
        all_fallback=all_fallback,
        mixed_quality_warning=mixed_quality_warning,
    )


# ---------------------------------------------------------------------------
# Aggregation entry point (swappable strategy)
# ---------------------------------------------------------------------------

def aggregate_lifts(
    tweets: list[AuthorNormalizedTweet],
    method: str = "weighted_mean",
) -> float:
    """Single entry point for lift aggregation. Strategy is swappable via config.

    Methods: 'weighted_mean' (default), 'weighted_median', 'winsorized_mean'
    """
    if not tweets:
        return 0.0

    if method == "weighted_mean":
        return weighted_mean_lift(tweets)
    elif method == "weighted_median":
        raise NotImplementedError(
            "weighted_median is not yet implemented. "
            "Set pulse_meta.aggregation_method to 'weighted_mean' in config.yaml."
        )
    elif method == "winsorized_mean":
        raise NotImplementedError(
            "winsorized_mean is not yet implemented. "
            "Set pulse_meta.aggregation_method to 'weighted_mean' in config.yaml."
        )
    else:
        return weighted_mean_lift(tweets)
