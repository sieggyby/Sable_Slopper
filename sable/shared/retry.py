"""Retry helpers with exponential backoff."""
from __future__ import annotations

import asyncio
import logging
import random
import time

logger = logging.getLogger(__name__)


def retry_with_backoff(fn, max_retries=3, base_delay=1.0):
    """Sync retry for stage2.py, selector.py."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logger.debug("Retry attempt %d/%d failed: %s", attempt + 1, max_retries, e)
            time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))


async def retry_with_backoff_async(coro_fn, max_retries=3, base_delay=1.0):
    """Async retry for scanner.py (asyncio — do not use time.sleep here)."""
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logger.debug("Retry attempt %d/%d failed: %s", attempt + 1, max_retries, e)
            await asyncio.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))
