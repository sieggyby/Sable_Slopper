"""Tests for vault/enrich.py — _enrich_chunk and enrich_batch."""
from __future__ import annotations

import json

import pytest

from sable.vault.config import VaultConfig
from sable.vault.enrich import _enrich_chunk, enrich_batch


def _make_config(batch_size: int = 10) -> VaultConfig:
    return VaultConfig(enrich_batch_size=batch_size)


def _make_items(n: int) -> list[dict]:
    return [{"id": f"item-{i}", "type": "clip", "topic": f"topic {i}"} for i in range(n)]


def _make_call_fn(enriched: list[dict]):
    """Returns a call_fn that responds with the given enriched list."""
    def call_fn(prompt):
        return json.dumps(enriched)
    return call_fn


# ─────────────────────────────────────────────────────────────────────
# _enrich_chunk
# ─────────────────────────────────────────────────────────────────────

def test_enrich_chunk_calls_call_fn_once_per_chunk():
    items = _make_items(3)
    calls = []
    enriched_response = [
        {"id": f"item-{i}", "topics": ["defi"], "questions_answered": [], "depth": "intro", "tone": "neutral", "keywords": []}
        for i in range(3)
    ]

    def call_fn(prompt):
        calls.append(prompt)
        return json.dumps(enriched_response)

    config = _make_config(batch_size=3)
    _enrich_chunk(items, ["defi"], config, call_fn)
    assert len(calls) == 1


def test_enrich_chunk_parses_list_response():
    items = _make_items(2)
    enriched_response = [
        {"id": "item-0", "topics": ["nft"], "questions_answered": ["What is NFT?"], "depth": "intro", "tone": "hype", "keywords": ["nft"]},
        {"id": "item-1", "topics": ["defi"], "questions_answered": [], "depth": "advanced", "tone": "analytical", "keywords": []},
    ]
    call_fn = _make_call_fn(enriched_response)
    config = _make_config()

    result = _enrich_chunk(items, [], config, call_fn)
    assert result[0]["topics"] == ["nft"]
    assert result[0]["enrichment_status"] == "done"
    assert result[1]["depth"] == "advanced"


def test_enrich_chunk_parses_dict_with_items_key():
    items = _make_items(1)
    enriched_data = [{"id": "item-0", "topics": ["layer2"], "questions_answered": [], "depth": "intermediate", "tone": "educational", "keywords": ["eth"]}]

    def call_fn(prompt):
        return json.dumps({"items": enriched_data})

    config = _make_config()
    result = _enrich_chunk(items, [], config, call_fn)
    assert result[0]["topics"] == ["layer2"]
    assert result[0]["enrichment_status"] == "done"


def test_enrich_chunk_marks_pending_on_call_failure():
    items = _make_items(2)

    def call_fn(prompt):
        raise RuntimeError("Claude is down")

    config = _make_config()
    # _enrich_chunk propagates the exception; enrich_batch catches it and marks pending
    with pytest.raises(RuntimeError):
        _enrich_chunk(items, [], config, call_fn)


# ─────────────────────────────────────────────────────────────────────
# enrich_batch
# ─────────────────────────────────────────────────────────────────────

def test_enrich_batch_empty_input_returns_empty(monkeypatch):
    # call_claude_json must not be called at all for empty input
    called = []

    def fake_call(prompt, **kw):
        called.append(prompt)
        return "[]"

    monkeypatch.setattr("sable.vault.enrich._enrich_chunk", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called")))
    config = _make_config()
    result = enrich_batch([], [], config)
    assert result == []
    assert called == []


def test_enrich_batch_splits_into_multiple_chunks(monkeypatch):
    """5 items with batch_size=2 → 3 Claude calls."""
    items = _make_items(5)
    call_counts = []

    def fake_enrich_chunk(chunk, org_topics, config, call_fn):
        call_counts.append(len(chunk))
        return [dict(item, enrichment_status="done", topics=[], questions_answered=[], depth="", tone="", keywords=[]) for item in chunk]

    monkeypatch.setattr("sable.vault.enrich._enrich_chunk", fake_enrich_chunk)
    # We still need call_claude_json to exist since enrich_batch imports it
    monkeypatch.setattr("sable.shared.api.call_claude_json", lambda prompt, **kw: "[]")

    config = _make_config(batch_size=2)
    result = enrich_batch(items, [], config)
    assert len(call_counts) == 3  # chunks: [2, 2, 1]
    assert len(result) == 5


def test_enrich_batch_marks_pending_on_chunk_failure(monkeypatch):
    items = _make_items(3)

    def fake_enrich_chunk(chunk, org_topics, config, call_fn):
        raise RuntimeError("API error")

    monkeypatch.setattr("sable.vault.enrich._enrich_chunk", fake_enrich_chunk)
    monkeypatch.setattr("sable.shared.api.call_claude_json", lambda prompt, **kw: "[]")

    config = _make_config(batch_size=10)
    result = enrich_batch(items, [], config)
    assert all(r.get("enrichment_status") == "pending" for r in result)
