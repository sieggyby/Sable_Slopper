"""Individual cadence signals for silence gradient computation."""
from __future__ import annotations

import math

# Minimum rows per half-window for engagement and format signals
MIN_ROWS_PER_HALF = 5


def compute_volume_drop(recent: int, prior: int) -> tuple[float, bool]:
    """Volume drop: 1 - (recent / max(prior, 1)), clamped [0, 1].

    Returns (score, insufficient). Insufficient when both halves are zero.
    """
    if recent == 0 and prior == 0:
        return 0.0, True
    score = 1.0 - (recent / max(prior, 1))
    return max(0.0, min(1.0, score)), False


def compute_engagement_drop(
    median_recent: float,
    median_prior: float,
    recent_count: int,
    prior_count: int,
) -> tuple[float, bool]:
    """Engagement drop: 1 - (median_recent / max(median_prior, 0.01)), clamped [0, 1].

    Requires >=MIN_ROWS_PER_HALF rows per half. Returns (score, insufficient).
    """
    if recent_count < MIN_ROWS_PER_HALF or prior_count < MIN_ROWS_PER_HALF:
        return 0.0, True

    score = 1.0 - (median_recent / max(median_prior, 0.01))
    return max(0.0, min(1.0, score)), False


def compute_format_regression(format_counts: dict[str, int]) -> tuple[float, bool]:
    """Format regression: inverted normalized Shannon entropy.

    High entropy = diverse formats = healthy. Low entropy = regression.
    Score = 1 - H_norm. Requires >=MIN_ROWS_PER_HALF total posts.
    Returns (score, insufficient).
    """
    total = sum(format_counts.values())
    if total < MIN_ROWS_PER_HALF:
        return 0.0, True

    n_categories = len(format_counts)
    if n_categories <= 1:
        return 1.0, False  # Single format = max regression

    # Shannon entropy
    entropy = 0.0
    for count in format_counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)

    max_entropy = math.log2(n_categories)
    normalized = entropy / max_entropy if max_entropy > 0 else 0.0

    return max(0.0, min(1.0, 1.0 - normalized)), False
