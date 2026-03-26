"""Trend detection and classification with dual baselines."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sable.pulse.meta.normalize import AuthorNormalizedTweet
from sable.pulse.meta.quality import EngagementQuality, aggregate_lifts, assess_format_quality


@dataclass
class TrendResult:
    format_bucket: str
    current_lift: float
    lift_vs_30d: Optional[float]    # current / 30d baseline
    lift_vs_7d: Optional[float]     # current / 7d baseline
    trend_status: Optional[str]     # surging|rising|stable|declining|dead|None
    momentum: Optional[str]         # accelerating|plateauing|decelerating|None
    confidence: str                 # A|B|C
    confidence_reasons: list[str]
    quality: EngagementQuality
    reasons: list[str]              # human-readable explanation
    gate_failures: list[str]        # why quality gates failed (if any)


def classify_trend(lift_vs_30d: float, cfg: dict | None = None) -> str:
    """Classify trend status from lift vs 30-day baseline."""
    cfg = cfg or {}
    surging = cfg.get("surging_threshold", 2.5)
    rising = cfg.get("rising_threshold", 1.5)
    declining = cfg.get("declining_threshold", 0.8)
    dead = cfg.get("dead_threshold", 0.5)

    if lift_vs_30d >= surging:
        return "surging"
    elif lift_vs_30d >= rising:
        return "rising"
    elif lift_vs_30d >= declining:
        return "stable"
    elif lift_vs_30d >= dead:
        return "declining"
    else:
        return "dead"


def classify_momentum(lift_vs_30d: float, lift_vs_7d: float) -> str:
    """Classify momentum from ratio of 7d vs 30d performance.

    accelerating: 7d significantly better than 30d (>= 1.3x)
    plateauing:   7d roughly matches 30d (0.85-1.3x)
    decelerating: 7d worse than 30d (< 0.85x)
    """
    if lift_vs_30d == 0:
        return "plateauing"
    ratio = lift_vs_7d / lift_vs_30d
    if ratio >= 1.3:
        return "accelerating"
    elif ratio >= 0.85:
        return "plateauing"
    else:
        return "decelerating"


def analyze_format_trend(
    format_bucket: str,
    tweets: list[AuthorNormalizedTweet],
    baseline_30d: Optional[float],
    baseline_7d: Optional[float],
    baseline_days_available: int,
    cfg: dict | None = None,
    method: str = "weighted_mean",
) -> TrendResult:
    """Analyze trend for a single format bucket.

    Quality gates enforced before any trend label:
    - Minimum 4 tweets in bucket
    - Minimum 2 unique authors
    - Minimum 5 days of baseline data
    """
    cfg = cfg or {}
    min_samples = cfg.get("min_samples_for_trend", 4)
    min_authors = cfg.get("min_authors_for_trend", 2)
    min_baseline_days = cfg.get("min_baseline_days", 5)

    quality = assess_format_quality(tweets)
    current_lift = aggregate_lifts(tweets, method=method)

    gate_failures: list[str] = []
    reasons: list[str] = []

    # Quality gates
    if quality.sample_count < min_samples:
        gate_failures.append(
            f"insufficient sample ({quality.sample_count} tweets, need {min_samples})"
        )
    if quality.unique_authors < min_authors:
        gate_failures.append(
            f"insufficient unique authors ({quality.unique_authors}, need {min_authors})"
        )
    if baseline_days_available < min_baseline_days:
        gate_failures.append(
            f"insufficient baseline ({baseline_days_available} days, need {min_baseline_days})"
        )
    if baseline_30d is None:
        gate_failures.append("no 30-day baseline available")

    if gate_failures:
        # Show raw numbers, no trend label
        reasons.append(f"Raw lift: {current_lift:.2f}x — no trend label (gates not met)")
        return TrendResult(
            format_bucket=format_bucket,
            current_lift=current_lift,
            lift_vs_30d=None,
            lift_vs_7d=None,
            trend_status=None,
            momentum=None,
            confidence=quality.confidence,
            confidence_reasons=quality.confidence_reasons,
            quality=quality,
            reasons=reasons,
            gate_failures=gate_failures,
        )

    # Compute ratios
    lift_vs_30d = current_lift / baseline_30d if baseline_30d else None
    lift_vs_7d = (current_lift / baseline_7d) if (baseline_7d and baseline_7d > 0) else None

    trend_status = classify_trend(lift_vs_30d, cfg) if lift_vs_30d is not None else None
    momentum = None
    if lift_vs_30d is not None and lift_vs_7d is not None:
        momentum = classify_momentum(lift_vs_30d, lift_vs_7d)

    # Build human-readable reasons
    reasons.append(
        f"Current lift: {current_lift:.2f}x | "
        f"vs 30d baseline: {lift_vs_30d:.2f}x" if lift_vs_30d else f"Current lift: {current_lift:.2f}x"
    )
    if lift_vs_7d is not None:
        reasons.append(f"vs 7d baseline: {lift_vs_7d:.2f}x ({momentum})")
    if quality.concentration > 0.50:
        reasons.append(
            f"Driven by {quality.unique_authors} authors "
            f"(top 2 = {quality.concentration:.0%} of signal)"
        )
    if quality.mixed_quality_warning:
        reasons.append(quality.mixed_quality_warning)

    return TrendResult(
        format_bucket=format_bucket,
        current_lift=current_lift,
        lift_vs_30d=lift_vs_30d,
        lift_vs_7d=lift_vs_7d,
        trend_status=trend_status,
        momentum=momentum,
        confidence=quality.confidence,
        confidence_reasons=quality.confidence_reasons,
        quality=quality,
        reasons=reasons,
        gate_failures=gate_failures,
    )


def analyze_all_formats(
    org: str,
    tweets_by_bucket: dict[str, list[AuthorNormalizedTweet]],
    baselines: dict[str, tuple[Optional[float], Optional[float]]],
    baseline_days_available: int,
    cfg: dict | None = None,
    method: str = "weighted_mean",
) -> dict[str, TrendResult]:
    """Analyze trend for every format bucket and return a full results map.

    Calls analyze_format_trend() for each bucket in tweets_by_bucket using the
    corresponding (lift_30d, lift_7d) pair from baselines. Returns
    {format_bucket: TrendResult} for all buckets.
    """
    results: dict[str, TrendResult] = {}
    for bucket, tweets in tweets_by_bucket.items():
        b30, b7 = baselines.get(bucket, (None, None))
        results[bucket] = analyze_format_trend(
            format_bucket=bucket,
            tweets=tweets,
            baseline_30d=b30,
            baseline_7d=b7,
            baseline_days_available=baseline_days_available,
            cfg=cfg,
            method=method,
        )
    return results
