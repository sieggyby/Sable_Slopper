"""Tests for sable/write/generator.py — Slice A context helpers."""
from __future__ import annotations

import json as _json
import sqlite3
import pytest
from pathlib import Path


def _make_meta_conn(scanned_tweets_rows: list[dict]) -> sqlite3.Connection:
    """Build an in-memory meta.db with scanned_tweets rows."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE scanned_tweets (
        tweet_id TEXT PRIMARY KEY, author_handle TEXT, format_bucket TEXT,
        org TEXT, total_lift REAL, author_quality_grade TEXT,
        author_quality_weight REAL, posted_at TEXT, text TEXT,
        attributes_json TEXT DEFAULT '[]',
        likes INTEGER DEFAULT 0, replies INTEGER DEFAULT 0,
        reposts INTEGER DEFAULT 0, quotes INTEGER DEFAULT 0,
        bookmarks INTEGER DEFAULT 0, video_views INTEGER DEFAULT 0,
        author_followers INTEGER DEFAULT 0,
        author_median_likes REAL DEFAULT 1.0, author_median_replies REAL DEFAULT 0.0,
        author_median_reposts REAL DEFAULT 0.0, author_median_quotes REAL DEFAULT 0.0,
        author_median_total REAL DEFAULT 1.0, author_median_same_format REAL DEFAULT 1.0
    )""")
    for i, r in enumerate(scanned_tweets_rows):
        conn.execute(
            """INSERT INTO scanned_tweets
               (tweet_id, author_handle, format_bucket, org, total_lift,
                author_quality_grade, author_quality_weight, posted_at)
               VALUES (?, ?, ?, ?, ?, 'adequate', 0.75, datetime('now', '-1 day'))""",
            (r.get("tweet_id", str(i)), r["author"], r["bucket"], r["org"], r["lift"]),
        )
    conn.commit()
    return conn


def test_select_best_format_returns_highest_lift():
    from sable.write.generator import _select_best_format
    conn = _make_meta_conn([
        {"author": "@a", "bucket": "standalone_text", "org": "testorg", "lift": 2.5},
        {"author": "@a", "bucket": "standalone_text", "org": "testorg", "lift": 2.5},
        {"author": "@b", "bucket": "short_clip", "org": "testorg", "lift": 1.2},
        {"author": "@b", "bucket": "short_clip", "org": "testorg", "lift": 1.2},
    ])
    result = _select_best_format("testorg", conn)
    assert result == "standalone_text"


def test_select_best_format_falls_back_to_standalone_text():
    from sable.write.generator import _select_best_format
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE scanned_tweets (tweet_id TEXT PRIMARY KEY)")
    conn.commit()
    result = _select_best_format("testorg", conn)
    assert result == "standalone_text"


def test_get_format_context_returns_trend_summary():
    from sable.write.generator import _get_format_context
    conn = _make_meta_conn([
        {"author": "@a", "bucket": "standalone_text", "org": "testorg", "lift": 2.5},
        {"author": "@a", "bucket": "standalone_text", "org": "testorg", "lift": 2.5},
        {"author": "@b", "bucket": "standalone_text", "org": "testorg", "lift": 2.5},
        {"author": "@b", "bucket": "standalone_text", "org": "testorg", "lift": 2.5},
    ])
    summary, examples = _get_format_context("testorg", "standalone_text", conn)
    assert "standalone_text" in summary
    assert "2." in summary  # lift in summary


def test_get_format_context_empty_examples_when_no_high_lift_tweets():
    from sable.write.generator import _get_format_context
    # No rows with total_lift >= 2.5
    conn = _make_meta_conn([
        {"author": "@a", "bucket": "standalone_text", "org": "testorg", "lift": 1.0},
        {"author": "@b", "bucket": "standalone_text", "org": "testorg", "lift": 1.0},
    ])
    _summary, examples = _get_format_context("testorg", "standalone_text", conn)
    assert examples == []


def test_get_vault_context_returns_none_when_no_topic():
    from sable.write.generator import _get_vault_context
    result = _get_vault_context(None, Path("/tmp"), "testorg")
    assert result is None


def test_get_vault_context_returns_none_when_vault_missing(tmp_path):
    from sable.write.generator import _get_vault_context
    result = _get_vault_context("defi", tmp_path / "nonexistent", "testorg")
    assert result is None


# ---------------------------------------------------------------------------
# Slice B — generate_tweet_variants helpers
# ---------------------------------------------------------------------------

def _make_account():
    from sable.roster.models import Account
    return Account(handle="@testwriter", org="testorg")


def _good_response(variants=None) -> str:
    if variants is None:
        variants = [
            {
                "text": "DeFi yields are compressing. Here's why.",
                "structural_move": "contrarian claim + specific number",
                "format_fit_score": 8.5,
                "notes": "punchy opener",
            }
        ]
    return _json.dumps({"variants": variants})


def test_generate_returns_list_of_variants(monkeypatch):
    from sable.write.generator import generate_tweet_variants

    monkeypatch.setattr("sable.write.generator.require_account", lambda h: _make_account())
    monkeypatch.setattr("sable.write.generator.build_account_context", lambda acc: "ctx")
    monkeypatch.setattr(
        "sable.write.generator.call_claude_json",
        lambda prompt, system="", **kwargs: _good_response(),
    )

    results = generate_tweet_variants(
        handle="@testwriter",
        org="testorg",
        format_bucket="standalone_text",
        topic="defi yields",
        source_url=None,
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
    )
    assert len(results) == 1
    assert results[0].text == "DeFi yields are compressing. Here's why."
    assert results[0].format_fit_score == 8.5


def test_generate_uses_best_format_when_bucket_is_none(monkeypatch):
    from sable.write.generator import generate_tweet_variants

    captured: dict = {}

    monkeypatch.setattr("sable.write.generator.require_account", lambda h: _make_account())
    monkeypatch.setattr("sable.write.generator.build_account_context", lambda acc: "ctx")
    monkeypatch.setattr("sable.write.generator._select_best_format", lambda org, conn: "short_clip")
    monkeypatch.setattr(
        "sable.write.generator._get_format_context",
        lambda org, bucket, conn: (f"{bucket} rising at 3.0x", []),
    )
    monkeypatch.setattr(
        "sable.write.generator.call_claude_json",
        lambda prompt, system="", **kwargs: (captured.update({"prompt": prompt}) or _good_response()),
    )

    # Need a real meta_db_path so conn is opened (enabling _select_best_format path)
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        generate_tweet_variants(
            handle="@testwriter",
            org="testorg",
            format_bucket=None,
            topic="test",
            source_url=None,
            num_variants=1,
            meta_db_path=db_path,
            vault_root=None,
        )
    finally:
        os.unlink(db_path)

    assert "short_clip" in captured["prompt"]


def test_generate_falls_back_to_standalone_text_when_no_meta_db(monkeypatch):
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
        format_bucket=None,
        topic="test",
        source_url=None,
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
    )

    assert "standalone_text" in captured["prompt"]


def test_generate_includes_vault_context_in_prompt(monkeypatch):
    from sable.write.generator import generate_tweet_variants

    captured: dict = {}

    monkeypatch.setattr("sable.write.generator.require_account", lambda h: _make_account())
    monkeypatch.setattr("sable.write.generator.build_account_context", lambda acc: "ctx")
    monkeypatch.setattr(
        "sable.write.generator._get_vault_context",
        lambda topic, vault_path, org: "Vault context: DeFi Yields — key note about rates",
    )
    monkeypatch.setattr(
        "sable.write.generator.call_claude_json",
        lambda prompt, system="", **kwargs: (captured.update({"prompt": prompt}) or _good_response()),
    )

    generate_tweet_variants(
        handle="@testwriter",
        org="testorg",
        format_bucket="standalone_text",
        topic="defi yields",
        source_url=None,
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
    )

    assert "Vault context: DeFi Yields" in captured["prompt"]


def test_generate_skips_vault_context_when_none(monkeypatch):
    from sable.write.generator import generate_tweet_variants

    captured: dict = {}

    monkeypatch.setattr("sable.write.generator.require_account", lambda h: _make_account())
    monkeypatch.setattr("sable.write.generator.build_account_context", lambda acc: "ctx")
    monkeypatch.setattr(
        "sable.write.generator._get_vault_context",
        lambda topic, vault_path, org: None,
    )
    monkeypatch.setattr(
        "sable.write.generator.call_claude_json",
        lambda prompt, system="", **kwargs: (captured.update({"prompt": prompt}) or _good_response()),
    )

    generate_tweet_variants(
        handle="@testwriter",
        org="testorg",
        format_bucket="standalone_text",
        topic="defi yields",
        source_url=None,
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
    )

    assert "Vault context" not in captured["prompt"]


def test_generate_returns_empty_list_on_bad_json(monkeypatch):
    from sable.write.generator import generate_tweet_variants

    monkeypatch.setattr("sable.write.generator.require_account", lambda h: _make_account())
    monkeypatch.setattr("sable.write.generator.build_account_context", lambda acc: "ctx")
    monkeypatch.setattr(
        "sable.write.generator.call_claude_json",
        lambda prompt, system="", **kwargs: "not json",
    )

    results = generate_tweet_variants(
        handle="@testwriter",
        org="testorg",
        format_bucket="standalone_text",
        topic=None,
        source_url=None,
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
    )
    assert results == []


def test_generate_returns_empty_list_when_variants_key_missing(monkeypatch):
    from sable.write.generator import generate_tweet_variants

    monkeypatch.setattr("sable.write.generator.require_account", lambda h: _make_account())
    monkeypatch.setattr("sable.write.generator.build_account_context", lambda acc: "ctx")
    monkeypatch.setattr(
        "sable.write.generator.call_claude_json",
        lambda prompt, system="", **kwargs: _json.dumps({"other": []}),
    )

    results = generate_tweet_variants(
        handle="@testwriter",
        org="testorg",
        format_bucket="standalone_text",
        topic=None,
        source_url=None,
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
    )
    assert results == []


def test_generate_passes_source_url_in_prompt(monkeypatch):
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
        source_url="https://t.co/abc",
        num_variants=1,
        meta_db_path=None,
        vault_root=None,
    )

    assert "https://t.co/abc" in captured["prompt"]
