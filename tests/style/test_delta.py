"""Tests for sable.style.delta — gap computation."""
from __future__ import annotations

import pytest

from sable.style.delta import compute_delta


def test_basic_gap():
    """Positive gap = managed under-indexes."""
    managed = {"text": 0.8, "clip": 0.2}
    watchlist = {"text": 0.5, "clip": 0.5}
    delta = compute_delta(managed, watchlist)

    assert delta is not None
    assert delta["text"] == pytest.approx(-0.3, abs=0.001)
    assert delta["clip"] == pytest.approx(0.3, abs=0.001)


def test_missing_bucket_in_managed():
    """Bucket in watchlist but not managed → full gap."""
    managed = {"text": 1.0}
    watchlist = {"text": 0.6, "clip": 0.4}
    delta = compute_delta(managed, watchlist)

    assert delta is not None
    assert delta["clip"] == pytest.approx(0.4, abs=0.001)
    assert delta["text"] == pytest.approx(-0.4, abs=0.001)


def test_empty_managed_returns_none():
    """Empty managed fingerprint → None."""
    assert compute_delta({}, {"text": 1.0}) is None


def test_empty_watchlist_returns_none():
    """Empty watchlist fingerprint → None."""
    assert compute_delta({"text": 1.0}, {}) is None


def test_both_empty_returns_none():
    """Both empty → None."""
    assert compute_delta({}, {}) is None


def test_enrichment_keys_included():
    """Enrichment keys (media_rate, link_rate) are included in delta."""
    managed = {"text": 0.5, "media_rate": 0.3}
    watchlist = {"text": 0.5, "media_rate": 0.7}
    delta = compute_delta(managed, watchlist)

    assert delta is not None
    assert delta["media_rate"] == pytest.approx(0.4, abs=0.001)
    assert delta["text"] == pytest.approx(0.0, abs=0.001)
