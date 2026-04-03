"""Shared SocialData API client with 402/429/5xx handling per best practices.

All SocialData HTTP calls must go through ``socialdata_get`` or
``socialdata_get_async`` so that error handling is consistent:

* **402** — balance exhausted.  Immediately fatal, no retry.
* **429** — rate-limited.  Exponential backoff with jitter (up to 4 retries).
* **5xx** — server error.  Retried with backoff, same schedule as 429.
* Other 4xx — raised immediately via ``raise_for_status()``.
"""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

from sable import config as cfg

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.socialdata.tools"

# Backoff schedule (seconds) per best practices doc Section 4:
# Attempt 1: ~1s, Attempt 2: ~4s, Attempt 3: ~16s, Attempt 4: ~64s
_MAX_RETRIES = 4
_BASE_DELAY = 1.0


class BalanceExhaustedError(Exception):
    """SocialData returned 402 — account balance is zero.  No retry will help."""


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {cfg.require_key('socialdata_api_key')}",
        "Content-Type": "application/json",
    }


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: nominal * (0.5 + random())."""
    nominal = _BASE_DELAY * (4 ** attempt)  # 1, 4, 16, 64
    return nominal * (0.5 + random.random())


async def socialdata_get_async(
    path: str,
    params: dict | None = None,
    timeout: float = 30,
) -> dict:
    """Make a GET request to SocialData with proper error handling.

    ``path`` is appended to the base URL, e.g. ``/twitter/user/handle/tweets``.

    Returns the parsed JSON response body.

    Raises:
        BalanceExhaustedError: on HTTP 402 (no retry).
        httpx.HTTPStatusError: on non-retryable 4xx.
        httpx.HTTPStatusError: on 5xx/429 after exhausting retries.
    """
    url = f"{_BASE_URL}{path}"
    last_exc: Exception | None = None

    async with httpx.AsyncClient(headers=_get_headers(), timeout=timeout) as client:
        for attempt in range(_MAX_RETRIES + 1):  # 0..4 = 5 total attempts
            try:
                resp = await client.get(url, params=params)
            except httpx.HTTPError as exc:
                # Network-level error (timeout, DNS, connection reset)
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _backoff_delay(attempt)
                    logger.warning("SocialData network error on %s (attempt %d): %s — retrying in %.1fs", path, attempt + 1, exc, delay)
                    await asyncio.sleep(delay)
                    continue
                raise

            if resp.status_code == 402:
                raise BalanceExhaustedError(
                    f"SocialData balance exhausted (HTTP 402) on {path}. "
                    "Top up your account — no retry will help."
                )

            if resp.status_code in (429, 500, 502, 503, 504):
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
                if attempt < _MAX_RETRIES:
                    delay = _backoff_delay(attempt)
                    logger.warning("SocialData %d on %s (attempt %d) — retrying in %.1fs", resp.status_code, path, attempt + 1, delay)
                    await asyncio.sleep(delay)
                    continue
                # Exhausted retries
                resp.raise_for_status()

            # Any other 4xx — raise immediately
            resp.raise_for_status()
            return resp.json()

    # Should never reach here, but satisfy type checker
    raise last_exc or RuntimeError("SocialData request failed")  # pragma: no cover


def socialdata_get(
    path: str,
    params: dict | None = None,
    timeout: float = 30,
) -> dict:
    """Sync wrapper around ``socialdata_get_async``."""
    return asyncio.run(socialdata_get_async(path, params=params, timeout=timeout))
