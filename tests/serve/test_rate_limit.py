"""Tests for in-process rate limiter."""
from __future__ import annotations

from sable.serve.rate_limit import RateLimiter


def test_allows_requests_under_limit():
    """Requests under the limit pass through."""
    limiter = RateLimiter(requests_per_minute=5)
    for _ in range(5):
        assert limiter.check("/api/test") is None


def test_blocks_at_limit():
    """Request at the limit returns a Retry-After value."""
    limiter = RateLimiter(requests_per_minute=3)
    for _ in range(3):
        limiter.check("/api/test")
    retry = limiter.check("/api/test")
    assert retry is not None
    assert retry >= 1


def test_separate_paths_independent():
    """Different paths have independent limits."""
    limiter = RateLimiter(requests_per_minute=2)
    limiter.check("/api/a")
    limiter.check("/api/a")
    # /api/a is at limit
    assert limiter.check("/api/a") is not None
    # /api/b still has capacity
    assert limiter.check("/api/b") is None


def test_minimum_rpm_is_one():
    """RPM cannot be set below 1."""
    limiter = RateLimiter(requests_per_minute=0)
    assert limiter._rpm == 1
    assert limiter.check("/test") is None
    assert limiter.check("/test") is not None


def test_window_expiry_allows_requests_again():
    """After the window expires, requests are allowed again."""
    from unittest.mock import patch
    import time as time_mod

    limiter = RateLimiter(requests_per_minute=2)
    base = time_mod.monotonic()

    with patch("sable.serve.rate_limit.time.monotonic", return_value=base):
        limiter.check("/api/test")
        limiter.check("/api/test")

    # At limit
    with patch("sable.serve.rate_limit.time.monotonic", return_value=base + 1):
        assert limiter.check("/api/test") is not None

    # After window expires (61s later)
    with patch("sable.serve.rate_limit.time.monotonic", return_value=base + 61):
        assert limiter.check("/api/test") is None


def test_path_params_collapsed_same_client():
    """Path params (org slugs) are collapsed for the same client."""
    limiter = RateLimiter(requests_per_minute=2)
    limiter.check("/api/vault/inventory/org1", client="alice")
    limiter.check("/api/vault/inventory/org2", client="alice")
    # Both count against alice:/api/vault/inventory
    assert limiter.check("/api/vault/inventory/org3", client="alice") is not None


def test_different_clients_independent():
    """Different authenticated clients get independent rate-limit buckets."""
    limiter = RateLimiter(requests_per_minute=2)
    limiter.check("/api/vault/inventory/org1", client="alice")
    limiter.check("/api/vault/inventory/org2", client="alice")
    # alice is at limit
    assert limiter.check("/api/vault/inventory/org3", client="alice") is not None
    # bob still has capacity on the same route
    assert limiter.check("/api/vault/inventory/org1", client="bob") is None


def test_anonymous_does_not_consume_authenticated_budget():
    """Anonymous traffic does not eat into an authenticated client's bucket."""
    limiter = RateLimiter(requests_per_minute=2)
    # Anonymous caller fills its own bucket
    limiter.check("/api/vault/inventory/x")
    limiter.check("/api/vault/inventory/y")
    assert limiter.check("/api/vault/inventory/z") is not None
    # Authenticated client is unaffected
    assert limiter.check("/api/vault/inventory/x", client="alice") is None


def test_lru_eviction_preserves_recently_used():
    """T3-6: Fill 100 keys, touch key #1 recently, evict with key #101 — key #1 survives."""
    from unittest.mock import patch
    import time as time_mod
    import sable.serve.rate_limit as rl

    orig_max = rl._MAX_KEYS
    rl._MAX_KEYS = 5  # small cap for test
    try:
        limiter = RateLimiter(requests_per_minute=100)
        base = time_mod.monotonic()

        # Fill 5 keys at time base
        with patch("sable.serve.rate_limit.time.monotonic", return_value=base):
            for i in range(5):
                limiter.check(f"/api/route{i}")

        # Touch key 0 at time base+10 (most recently used)
        with patch("sable.serve.rate_limit.time.monotonic", return_value=base + 10):
            limiter.check("/api/route0")

        # Add key 5 — should evict the LRU key (one of route1-4), NOT route0
        with patch("sable.serve.rate_limit.time.monotonic", return_value=base + 11):
            limiter.check("/api/route5")

        # route0 should still have its bucket
        key0 = "__anonymous__:/api/route0"
        assert key0 in limiter._timestamps
    finally:
        rl._MAX_KEYS = orig_max
