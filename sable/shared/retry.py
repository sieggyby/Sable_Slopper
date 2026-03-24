"""Retry helpers with exponential backoff."""
from __future__ import annotations

import asyncio
import random
import time


def retry_with_backoff(fn, max_retries=3, base_delay=1.0):
    """Sync retry for stage2.py, selector.py."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))


async def retry_with_backoff_async(coro_fn, max_retries=3, base_delay=1.0):
    """Async retry for scanner.py (asyncio — do not use time.sleep here)."""
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except Exception:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))
