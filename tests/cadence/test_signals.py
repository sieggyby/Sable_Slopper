"""Tests for sable.cadence.signals — individual cadence signal computations."""
from __future__ import annotations

import math

import pytest

from sable.cadence.signals import (
    compute_volume_drop,
    compute_engagement_drop,
    compute_format_regression,
    MIN_ROWS_PER_HALF,
)


# ---------------------------------------------------------------------------
# compute_volume_drop
# ---------------------------------------------------------------------------

def test_volume_drop_full():
    """Recent=0, prior=10 → drop=1.0."""
    score, insuf = compute_volume_drop(0, 10)
    assert score == pytest.approx(1.0)
    assert insuf is False


def test_volume_drop_none():
    """Recent=10, prior=10 → drop=0.0."""
    score, insuf = compute_volume_drop(10, 10)
    assert score == pytest.approx(0.0)
    assert insuf is False


def test_volume_drop_half():
    """Recent=5, prior=10 → drop=0.5."""
    score, insuf = compute_volume_drop(5, 10)
    assert score == pytest.approx(0.5)


def test_volume_drop_growth_clamped():
    """Recent > prior → negative clamped to 0."""
    score, insuf = compute_volume_drop(15, 10)
    assert score == 0.0


def test_volume_drop_both_zero_insufficient():
    """Both halves zero → insufficient, not max drop."""
    score, insuf = compute_volume_drop(0, 0)
    assert insuf is True
    assert score == pytest.approx(0.0)


def test_volume_drop_zero_prior_nonzero_recent():
    """Prior=0, recent>0 → uses max(prior, 1), growth clamped to 0."""
    score, insuf = compute_volume_drop(5, 0)
    assert score == pytest.approx(0.0)
    assert insuf is False


# ---------------------------------------------------------------------------
# compute_engagement_drop
# ---------------------------------------------------------------------------

def test_engagement_drop_basic():
    """Known medians produce expected drop."""
    score, insuf = compute_engagement_drop(5.0, 10.0, 10, 10)
    assert score == pytest.approx(0.5)
    assert insuf is False


def test_engagement_drop_insufficient_recent():
    """Fewer than MIN_ROWS_PER_HALF recent → insufficient."""
    score, insuf = compute_engagement_drop(5.0, 10.0, 3, 10)
    assert score == 0.0
    assert insuf is True


def test_engagement_drop_insufficient_prior():
    """Fewer than MIN_ROWS_PER_HALF prior → insufficient."""
    score, insuf = compute_engagement_drop(5.0, 10.0, 10, 2)
    assert insuf is True


def test_engagement_drop_zero_prior_median():
    """Zero prior median → uses max(prior, 0.01)."""
    score, insuf = compute_engagement_drop(0.0, 0.0, 10, 10)
    assert score == pytest.approx(1.0)
    assert insuf is False


def test_engagement_drop_growth_clamped():
    """Median growth → clamped to 0."""
    score, insuf = compute_engagement_drop(20.0, 10.0, 10, 10)
    assert score == 0.0


def test_engagement_drop_tiny_prior_median():
    """Very small prior median uses 0.01 floor."""
    score, insuf = compute_engagement_drop(0.005, 0.001, 10, 10)
    # effective: 1 - (0.005 / 0.01) = 0.5
    assert score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# compute_format_regression
# ---------------------------------------------------------------------------

def test_format_regression_single():
    """Single format → max regression (1.0)."""
    score, insuf = compute_format_regression({"text": 10})
    assert score == pytest.approx(1.0)
    assert insuf is False


def test_format_regression_even():
    """Even distribution → entropy = max → regression near 0."""
    score, insuf = compute_format_regression({"text": 5, "clip": 5})
    assert score == pytest.approx(0.0)
    assert insuf is False


def test_format_regression_skewed():
    """Skewed distribution → partial regression."""
    score, insuf = compute_format_regression({"text": 9, "clip": 1})
    assert 0.0 < score < 1.0


def test_format_regression_insufficient():
    """Fewer than MIN_ROWS_PER_HALF → insufficient."""
    score, insuf = compute_format_regression({"text": 2})
    assert insuf is True


def test_format_regression_three_formats():
    """Three equal formats → entropy = log2(3)/log2(3) = 1 → score = 0."""
    score, insuf = compute_format_regression({"text": 5, "clip": 5, "quote": 5})
    assert score == pytest.approx(0.0, abs=0.01)
