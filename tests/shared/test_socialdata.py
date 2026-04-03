"""Tests for shared/socialdata.py — 402/429/5xx handling per best practices."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from sable.shared.socialdata import (
    socialdata_get_async,
    BalanceExhaustedError,
    _backoff_delay,
)


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Build a fake httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", "https://api.socialdata.tools/test"),
        json=json_data or {},
    )
    return resp


# ─────────────────────────────────────────────────────────────────────
# 402 — Balance Exhausted (fatal, no retry)
# ─────────────────────────────────────────────────────────────────────

def test_402_raises_balance_exhausted_immediately(monkeypatch):
    """HTTP 402 raises BalanceExhaustedError on first attempt, no retry."""
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-key")
    call_count = [0]

    async def fake_get(self, url, **kw):
        call_count[0] += 1
        return _mock_response(402)

    with patch.object(httpx.AsyncClient, "get", fake_get):
        with pytest.raises(BalanceExhaustedError, match="balance exhausted"):
            asyncio.run(socialdata_get_async("/test"))

    assert call_count[0] == 1  # No retries


# ─────────────────────────────────────────────────────────────────────
# 429 — Rate Limited (exponential backoff with jitter)
# ─────────────────────────────────────────────────────────────────────

def test_429_retries_with_backoff(monkeypatch):
    """HTTP 429 is retried up to 4 times with exponential backoff."""
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-key")
    monkeypatch.setattr("sable.shared.socialdata._backoff_delay", lambda a: 0.001)
    call_count = [0]

    async def fake_get(self, url, **kw):
        call_count[0] += 1
        if call_count[0] <= 3:
            return _mock_response(429)
        return _mock_response(200, {"ok": True})

    with patch.object(httpx.AsyncClient, "get", fake_get):
        result = asyncio.run(socialdata_get_async("/test"))

    assert result == {"ok": True}
    assert call_count[0] == 4  # 3 retries + 1 success


def test_429_exhausted_retries_raises(monkeypatch):
    """After 5 attempts on 429, raises HTTPStatusError."""
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-key")
    monkeypatch.setattr("sable.shared.socialdata._backoff_delay", lambda a: 0.001)
    call_count = [0]

    async def fake_get(self, url, **kw):
        call_count[0] += 1
        return _mock_response(429)

    with patch.object(httpx.AsyncClient, "get", fake_get):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(socialdata_get_async("/test"))

    assert call_count[0] == 5  # 1 initial + 4 retries


# ─────────────────────────────────────────────────────────────────────
# 5xx — Server Error (retried like 429)
# ─────────────────────────────────────────────────────────────────────

def test_5xx_retries_then_succeeds(monkeypatch):
    """5xx is retried, and succeeds if a subsequent attempt returns 200."""
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-key")
    monkeypatch.setattr("sable.shared.socialdata._backoff_delay", lambda a: 0.001)
    call_count = [0]

    async def fake_get(self, url, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _mock_response(503)
        return _mock_response(200, {"recovered": True})

    with patch.object(httpx.AsyncClient, "get", fake_get):
        result = asyncio.run(socialdata_get_async("/test"))

    assert result == {"recovered": True}
    assert call_count[0] == 2


# ─────────────────────────────────────────────────────────────────────
# 200 — Success (no retry)
# ─────────────────────────────────────────────────────────────────────

def test_200_returns_json(monkeypatch):
    """HTTP 200 returns parsed JSON body."""
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-key")

    async def fake_get(self, url, **kw):
        return _mock_response(200, {"tweets": [{"id": "1"}]})

    with patch.object(httpx.AsyncClient, "get", fake_get):
        result = asyncio.run(socialdata_get_async("/twitter/search", params={"q": "test"}))

    assert result == {"tweets": [{"id": "1"}]}


# ─────────────────────────────────────────────────────────────────────
# Other 4xx — Raised immediately (no retry)
# ─────────────────────────────────────────────────────────────────────

def test_404_raises_immediately(monkeypatch):
    """HTTP 404 raises HTTPStatusError on first attempt."""
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-key")
    call_count = [0]

    async def fake_get(self, url, **kw):
        call_count[0] += 1
        return _mock_response(404)

    with patch.object(httpx.AsyncClient, "get", fake_get):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(socialdata_get_async("/test"))

    assert call_count[0] == 1  # No retries


# ─────────────────────────────────────────────────────────────────────
# Network errors — retried with backoff
# ─────────────────────────────────────────────────────────────────────

def test_network_error_retried_then_succeeds(monkeypatch):
    """Network-level errors (timeout, DNS, connection reset) are retried."""
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-key")
    monkeypatch.setattr("sable.shared.socialdata._backoff_delay", lambda a: 0.001)
    call_count = [0]

    async def fake_get(self, url, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            raise httpx.ConnectError("Connection refused")
        return _mock_response(200, {"recovered": True})

    with patch.object(httpx.AsyncClient, "get", fake_get):
        result = asyncio.run(socialdata_get_async("/test"))

    assert result == {"recovered": True}
    assert call_count[0] == 2


def test_network_error_exhausted_raises(monkeypatch):
    """Network errors that persist through all retries are raised."""
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-key")
    monkeypatch.setattr("sable.shared.socialdata._backoff_delay", lambda a: 0.001)
    call_count = [0]

    async def fake_get(self, url, **kw):
        call_count[0] += 1
        raise httpx.ConnectError("Connection refused")

    with patch.object(httpx.AsyncClient, "get", fake_get):
        with pytest.raises(httpx.ConnectError):
            asyncio.run(socialdata_get_async("/test"))

    assert call_count[0] == 5  # 1 initial + 4 retries


# ─────────────────────────────────────────────────────────────────────
# Backoff schedule
# ─────────────────────────────────────────────────────────────────────

def test_backoff_delay_is_exponential():
    """Backoff delays follow exponential pattern with jitter."""
    # Each attempt should produce a delay in range [nominal*0.5, nominal*1.5)
    # nominal = 4^attempt: 1, 4, 16, 64
    for _ in range(20):
        d0 = _backoff_delay(0)
        d1 = _backoff_delay(1)
        d2 = _backoff_delay(2)
        d3 = _backoff_delay(3)
        assert 0.5 <= d0 < 1.5
        assert 2.0 <= d1 < 6.0
        assert 8.0 <= d2 < 24.0
        assert 32.0 <= d3 < 96.0
