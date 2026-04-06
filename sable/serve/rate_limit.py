"""In-process sliding-window rate limiter for sable serve."""
from __future__ import annotations

import re
import threading
import time
from collections import deque


# Extract route prefix (e.g., /api/vault/inventory/someorg → /api/vault/inventory)
# This prevents path-param cardinality from inflating the key space.
_PREFIX_RE = re.compile(r"^(/api/[^/]+/[^/]+)")

_MAX_KEYS = 100  # cap on distinct rate-limit buckets


class RateLimiter:
    """Sliding-window rate limiter keyed by route prefix.

    Thread-safe. No external dependencies. Keys are bounded by
    ``_MAX_KEYS`` to prevent unbounded memory growth.
    """

    def __init__(self, requests_per_minute: int = 60):
        self._rpm = max(1, requests_per_minute)
        self._window = 60.0  # seconds
        self._lock = threading.Lock()
        self._timestamps: dict[str, deque[float]] = {}

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Collapse path params into a fixed route prefix."""
        m = _PREFIX_RE.match(path)
        return m.group(1) if m else path

    def check(self, path: str, client: str = "__anonymous__") -> int | None:
        """Check if request is allowed.

        Returns None if allowed, or the number of seconds to wait
        (Retry-After value) if rate limit exceeded.  Keyed by
        ``client`` + normalized route so different clients get
        independent budgets.
        """
        key = f"{client}:{self._normalize_path(path)}"
        now = time.monotonic()
        cutoff = now - self._window

        with self._lock:
            ts = self._timestamps.get(key)
            if ts is None:
                if len(self._timestamps) >= _MAX_KEYS:
                    # Evict least-recently-used key
                    lru_key = min(
                        self._timestamps,
                        key=lambda k: self._timestamps[k][-1] if self._timestamps[k] else 0,
                    )
                    del self._timestamps[lru_key]
                ts = deque()
                self._timestamps[key] = ts

            # Evict expired timestamps (O(1) per pop from left of deque)
            while ts and ts[0] <= cutoff:
                ts.popleft()

            if len(ts) >= self._rpm:
                # Oldest request in window determines when a slot opens
                retry_after = int(ts[0] - cutoff) + 1
                return max(1, retry_after)

            ts.append(now)
            return None
