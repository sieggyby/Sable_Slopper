"""Style delta computation — gap analysis between managed and watchlist fingerprints."""
from __future__ import annotations


def compute_delta(
    managed_fp: dict[str, float],
    watchlist_fp: dict[str, float],
) -> dict[str, float] | None:
    """Compute per-bucket format gap: watchlist_share - managed_share.

    Returns None if either fingerprint is empty (below MIN_POSTS).
    Positive gap = managed account under-indexes vs watchlist.
    Negative gap = managed account over-indexes.
    """
    if not managed_fp or not watchlist_fp:
        return None

    # All coarse buckets present in either fingerprint
    all_buckets = set(managed_fp) | set(watchlist_fp)

    delta: dict[str, float] = {}
    for key in sorted(all_buckets):
        m_val = managed_fp.get(key, 0.0)
        w_val = watchlist_fp.get(key, 0.0)
        delta[key] = round(w_val - m_val, 4)

    return delta
