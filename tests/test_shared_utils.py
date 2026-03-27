"""Tests for shared/pricing.py, shared/files.py, shared/retry.py."""
from __future__ import annotations

import pytest

from sable.shared.pricing import compute_cost, CLAUDE_COST_PER_M_TOKENS
from sable.shared.files import atomic_write
from sable.shared.retry import retry_with_backoff


# ─────────────────────────────────────────────────────────────────────
# shared/pricing.py
# ─────────────────────────────────────────────────────────────────────

def test_compute_cost_known_sonnet_model():
    # sonnet: $3.0/M input, $15.0/M output
    # 1000 in + 500 out = 3.0/1000 + 15.0*0.5/1000 = 0.003 + 0.0075 = 0.0105
    cost = compute_cost(1000, 500, "claude-sonnet-4-6")
    assert cost == pytest.approx(0.0105)


def test_compute_cost_known_haiku_model():
    # haiku: $0.25/M input, $1.25/M output
    # 1000 in + 500 out = 0.25/1000 + 1.25*0.5/1000 = 0.00025 + 0.000625 = 0.000875
    cost = compute_cost(1000, 500, "claude-haiku-4-5-20251001")
    haiku_rates = CLAUDE_COST_PER_M_TOKENS["claude-haiku-4-5-20251001"]
    expected = (1000 * haiku_rates["input"] + 500 * haiku_rates["output"]) / 1_000_000
    assert cost == pytest.approx(expected)
    # haiku should be cheaper than sonnet for same tokens
    sonnet_cost = compute_cost(1000, 500, "claude-sonnet-4-6")
    assert cost < sonnet_cost


def test_compute_cost_unknown_model_uses_default():
    # Unknown model falls back to sonnet pricing ($3.0/$15.0)
    cost_unknown = compute_cost(1000, 500, "claude-unknown-model")
    cost_sonnet = compute_cost(1000, 500, "claude-sonnet-4-6")
    assert cost_unknown == pytest.approx(cost_sonnet)


def test_compute_cost_zero_tokens():
    assert compute_cost(0, 0, "claude-sonnet-4-6") == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────
# shared/files.py
# ─────────────────────────────────────────────────────────────────────

def test_atomic_write_creates_file_with_content(tmp_path):
    target = tmp_path / "out.md"
    atomic_write(target, "hello world")
    assert target.exists()
    assert target.read_text() == "hello world"


def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "dir" / "file.txt"
    atomic_write(target, "content")
    assert target.exists()
    assert target.read_text() == "content"


def test_atomic_write_leaves_no_temp_on_success(tmp_path):
    target = tmp_path / "out.md"
    atomic_write(target, "data")
    tmp_file = target.with_suffix(target.suffix + ".tmp")
    assert not tmp_file.exists()


# ─────────────────────────────────────────────────────────────────────
# shared/retry.py
# ─────────────────────────────────────────────────────────────────────

def test_retry_succeeds_on_first_attempt():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = retry_with_backoff(fn, max_retries=3, base_delay=0)
    assert result == "ok"
    assert len(calls) == 1


def test_retry_succeeds_on_second_attempt(monkeypatch):
    monkeypatch.setattr("sable.shared.retry.time.sleep", lambda _: None)
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("fail")
        return "ok"

    result = retry_with_backoff(fn, max_retries=3, base_delay=0)
    assert result == "ok"
    assert len(calls) == 2


def test_retry_exhausts_and_raises(monkeypatch):
    monkeypatch.setattr("sable.shared.retry.time.sleep", lambda _: None)
    calls = []

    def fn():
        calls.append(1)
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError, match="always fails"):
        retry_with_backoff(fn, max_retries=3, base_delay=0)
    assert len(calls) == 3


def test_retry_custom_max_retries(monkeypatch):
    monkeypatch.setattr("sable.shared.retry.time.sleep", lambda _: None)
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("fail")

    with pytest.raises(ValueError):
        retry_with_backoff(fn, max_retries=2, base_delay=0)
    assert len(calls) == 2


def test_retry_sleep_is_called_between_attempts(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("sable.shared.retry.time.sleep", lambda d: sleep_calls.append(d))
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("fail")
        return "done"

    retry_with_backoff(fn, max_retries=3, base_delay=1.0)
    # sleep called once between attempt 1→2 and once between 2→3 (2 sleeps total)
    assert len(sleep_calls) == 2
