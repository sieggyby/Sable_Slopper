"""Tests for watchlist_wire parameter in generate_tweet_variants."""
from __future__ import annotations

import json as _json
import sqlite3
from pathlib import Path
from unittest.mock import Mock


def _make_account():
    from sable.roster.models import Account
    return Account(handle="@testwriter", org="testorg")


def _good_response():
    return _json.dumps({"variants": [
        {
            "text": "DeFi yields are compressing.",
            "structural_move": "contrarian claim",
            "format_fit_score": 8.0,
            "notes": "",
        }
    ]})


def test_watchlist_wire_false_no_wire_block_in_prompt(monkeypatch):
    """watchlist_wire=False (default) — prompt must NOT contain the wire block phrase."""
    from sable.write.generator import generate_tweet_variants

    captured: dict = {}

    monkeypatch.setattr("sable.write.generator.require_account", lambda h: _make_account())
    monkeypatch.setattr("sable.write.generator.build_account_context", lambda acc: "ctx")
    monkeypatch.setattr(
        "sable.write.generator.call_claude_json",
        lambda prompt, system="", **kwargs: (captured.update({"prompt": prompt}) or _good_response()),
    )

    generate_tweet_variants(
        handle="@testwriter",
        org="testorg",
        format_bucket="standalone_text",
        topic="test",
        source_url=None,
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
        watchlist_wire=False,
    )

    assert "Trending niche topics" not in captured["prompt"]


def test_watchlist_wire_true_with_signals_injects_terms(monkeypatch):
    """watchlist_wire=True with signals present injects term names into prompt."""
    from sable.write.generator import generate_tweet_variants
    import sable.pulse.meta.db as meta_db_mod

    captured: dict = {}

    fake_signals = [
        {"term": "liquid staking", "avg_lift": 3.0, "acceleration": 2.0, "unique_authors": 5, "mention_count": 10},
        {"term": "defi yields", "avg_lift": 2.0, "acceleration": 1.5, "unique_authors": 3, "mention_count": 6},
        {"term": "nft royalties", "avg_lift": 1.5, "acceleration": 1.0, "unique_authors": 2, "mention_count": 4},
    ]

    monkeypatch.setattr("sable.write.generator.require_account", lambda h: _make_account())
    monkeypatch.setattr("sable.write.generator.build_account_context", lambda acc: "ctx")
    monkeypatch.setattr(
        "sable.write.generator.call_claude_json",
        lambda prompt, system="", **kwargs: (captured.update({"prompt": prompt}) or _good_response()),
    )
    # Patch get_top_topic_signals at the meta db module level
    monkeypatch.setattr(meta_db_mod, "get_top_topic_signals",
                        lambda org, limit=20, min_unique_authors=1, conn=None: fake_signals)

    generate_tweet_variants(
        handle="@testwriter",
        org="testorg",
        format_bucket="standalone_text",
        topic="test",
        source_url=None,
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
        watchlist_wire=True,
    )

    assert "Trending niche topics" in captured["prompt"]
    assert "liquid staking" in captured["prompt"]
    assert "defi yields" in captured["prompt"]
    assert "nft royalties" in captured["prompt"]


def test_watchlist_wire_true_no_meta_db_no_error(monkeypatch):
    """watchlist_wire=True with conn=None and no signals — no error, prompt unchanged."""
    from sable.write.generator import generate_tweet_variants
    import sable.pulse.meta.db as meta_db_mod

    captured: dict = {}

    monkeypatch.setattr("sable.write.generator.require_account", lambda h: _make_account())
    monkeypatch.setattr("sable.write.generator.build_account_context", lambda acc: "ctx")
    monkeypatch.setattr(
        "sable.write.generator.call_claude_json",
        lambda prompt, system="", **kwargs: (captured.update({"prompt": prompt}) or _good_response()),
    )
    # Return empty signals (as if no meta.db data)
    monkeypatch.setattr(meta_db_mod, "get_top_topic_signals",
                        lambda org, limit=20, min_unique_authors=1, conn=None: [])

    result = generate_tweet_variants(
        handle="@testwriter",
        org="testorg",
        format_bucket="standalone_text",
        topic="test",
        source_url=None,
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
        watchlist_wire=True,
    )

    # Should not crash, wire block absent since no signals
    assert "Trending niche topics" not in captured["prompt"]
    # Should still return variants
    assert len(result.variants) == 1
