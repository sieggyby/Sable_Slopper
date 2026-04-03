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
    def call_fn(prompt, **kw):
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

    def call_fn(prompt, **kw):
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

    def call_fn(prompt, **kw):
        return json.dumps({"items": enriched_data})

    config = _make_config()
    result = _enrich_chunk(items, [], config, call_fn)
    assert result[0]["topics"] == ["layer2"]
    assert result[0]["enrichment_status"] == "done"


def test_enrich_chunk_marks_pending_on_call_failure():
    items = _make_items(2)

    def call_fn(prompt, **kw):
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

    def fake_enrich_chunk(chunk, org_topics, config, call_fn, org=""):
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

    def fake_enrich_chunk(chunk, org_topics, config, call_fn, org=""):
        raise RuntimeError("API error")

    monkeypatch.setattr("sable.vault.enrich._enrich_chunk", fake_enrich_chunk)
    monkeypatch.setattr("sable.shared.api.call_claude_json", lambda prompt, **kw: "[]")

    config = _make_config(batch_size=10)
    result = enrich_batch(items, [], config)
    assert all(r.get("enrichment_status") == "pending" for r in result)


# ─────────────────────────────────────────────────────────────────────
# org_id threading and chunk failure warnings (Codex feedback)
# ─────────────────────────────────────────────────────────────────────

def test_enrich_chunk_passes_org_id_to_claude():
    """_enrich_chunk passes org_id kwarg to the call function."""
    captured = {}

    def fake_call(prompt, **kw):
        captured.update(kw)
        return json.dumps([{"id": "item-0", "topics": ["defi"], "keywords": ["test"]}])

    config = _make_config()
    items = _make_items(1)
    _enrich_chunk(items, ["defi"], config, fake_call, org="myorg")
    assert captured.get("org_id") == "myorg"


def test_enrich_chunk_empty_org_sends_none():
    """Empty org string sends org_id=None."""
    captured = {}

    def fake_call(prompt, **kw):
        captured.update(kw)
        return json.dumps([{"id": "item-0", "topics": ["defi"], "keywords": ["test"]}])

    config = _make_config()
    items = _make_items(1)
    _enrich_chunk(items, ["defi"], config, fake_call, org="")
    assert captured.get("org_id") is None


def test_enrich_batch_threads_org_to_claude(monkeypatch):
    """enrich_batch passes org through to call_claude_json."""
    captured = {}

    def fake_claude(prompt, **kw):
        captured.update(kw)
        return json.dumps([{"id": f"item-{i}", "topics": [], "keywords": []} for i in range(2)])

    monkeypatch.setattr("sable.shared.api.call_claude_json", fake_claude)
    config = _make_config()
    enrich_batch(_make_items(2), ["defi"], config, org="testorg")
    assert captured.get("org_id") == "testorg"


def test_enrich_batch_chunk_failure_emits_warning(monkeypatch):
    """Chunk failure logs a warning and marks items as pending."""
    from unittest.mock import patch as _patch

    def fake_enrich_chunk(chunk, org_topics, config, call_fn, org=""):
        raise RuntimeError("API error")

    monkeypatch.setattr("sable.vault.enrich._enrich_chunk", fake_enrich_chunk)
    monkeypatch.setattr("sable.shared.api.call_claude_json", lambda prompt, **kw: "[]")

    with _patch("sable.vault.enrich.logger") as mock_logger:
        config = _make_config(batch_size=10)
        result = enrich_batch(_make_items(2), [], config, org="testorg")

    assert all(r.get("enrichment_status") == "pending" for r in result)
    assert mock_logger.warning.called
    warning_args = str(mock_logger.warning.call_args)
    assert "Enrichment chunk failed" in warning_args
