"""Tests for viral anatomy DB helpers and analysis logic."""
from __future__ import annotations

import json
import sqlite3

import pytest

from sable.platform.errors import SableError


_SCHEMA = """
CREATE TABLE scanned_tweets (
    tweet_id TEXT PRIMARY KEY,
    author_handle TEXT NOT NULL,
    text TEXT,
    posted_at TEXT,
    format_bucket TEXT,
    attributes_json TEXT,
    likes INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0,
    quotes INTEGER DEFAULT 0,
    bookmarks INTEGER DEFAULT 0,
    video_views INTEGER DEFAULT 0,
    video_duration INTEGER,
    is_quote_tweet INTEGER DEFAULT 0,
    is_thread INTEGER DEFAULT 0,
    thread_length INTEGER DEFAULT 1,
    has_image INTEGER DEFAULT 0,
    has_video INTEGER DEFAULT 0,
    has_link INTEGER DEFAULT 0,
    author_followers INTEGER DEFAULT 0,
    author_median_likes REAL,
    author_median_replies REAL,
    author_median_reposts REAL,
    author_median_quotes REAL,
    author_median_total REAL,
    author_median_same_format REAL,
    likes_lift REAL,
    replies_lift REAL,
    reposts_lift REAL,
    quotes_lift REAL,
    total_lift REAL,
    format_lift REAL,
    author_quality_grade TEXT,
    author_quality_weight REAL,
    format_lift_reliable INTEGER DEFAULT 0,
    scan_id INTEGER,
    org TEXT
);
CREATE TABLE viral_anatomies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    tweet_id TEXT NOT NULL,
    author_handle TEXT NOT NULL,
    total_lift REAL NOT NULL,
    format_bucket TEXT NOT NULL,
    anatomy_json TEXT NOT NULL,
    analyzed_at TEXT NOT NULL,
    UNIQUE(org, tweet_id)
);
CREATE INDEX idx_viral_anatomies_org ON viral_anatomies (org);
"""

_SAMPLE_ANATOMY = {
    "hook_structure": "bold claim",
    "hook_length_words": 5,
    "first_sentence": "This will change everything.",
    "emotional_register": "excited",
    "topic_cluster": "DeFi yields",
    "has_cta": False,
    "cta_type": None,
    "retweet_bait": True,
    "retweet_bait_element": "controversial prediction",
    "is_thread": False,
    "thread_length": None,
}


class _NoClose:
    """Proxy that makes close() a no-op so monkeypatched get_conn() stays open."""
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.row_factory = conn.row_factory

    def execute(self, *a, **kw):
        return self._conn.execute(*a, **kw)

    def executemany(self, *a, **kw):
        return self._conn.executemany(*a, **kw)

    def executescript(self, *a, **kw):
        return self._conn.executescript(*a, **kw)

    def commit(self):
        return self._conn.commit()

    def close(self):
        pass

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *a):
        return self._conn.__exit__(*a)


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _insert_tweet(conn, tweet_id, author_handle, text, format_bucket, total_lift, org):
    conn.execute(
        "INSERT INTO scanned_tweets (tweet_id, author_handle, text, format_bucket, total_lift, org) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tweet_id, author_handle, text, format_bucket, total_lift, org),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def test_save_anatomy_inserts_row(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    db_mod.save_anatomy(
        org="testorg",
        tweet_id="t1",
        author_handle="alice",
        total_lift=15.0,
        format_bucket="standalone_text",
        anatomy_json=json.dumps(_SAMPLE_ANATOMY),
    )

    row = conn.execute("SELECT * FROM viral_anatomies WHERE tweet_id='t1'").fetchone()
    assert row is not None
    assert row["org"] == "testorg"
    assert row["author_handle"] == "alice"
    assert row["total_lift"] == 15.0
    assert row["format_bucket"] == "standalone_text"
    assert json.loads(row["anatomy_json"]) == _SAMPLE_ANATOMY
    assert row["analyzed_at"] is not None


def test_save_anatomy_duplicate_ignored(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    db_mod.save_anatomy("testorg", "t1", "alice", 15.0, "standalone_text", json.dumps(_SAMPLE_ANATOMY))
    db_mod.save_anatomy("testorg", "t1", "alice", 20.0, "standalone_text", json.dumps(_SAMPLE_ANATOMY))

    count = conn.execute("SELECT COUNT(*) FROM viral_anatomies").fetchone()[0]
    assert count == 1


def test_get_unanalyzed_returns_above_threshold(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    _insert_tweet(conn, "t_high", "alice", "big alpha drop", "standalone_text", 12.0, "testorg")
    _insert_tweet(conn, "t_low", "bob", "meh post", "standalone_text", 5.0, "testorg")

    results = db_mod.get_unanalyzed_viral_tweets("testorg", lift_threshold=10.0)
    assert len(results) == 1
    assert results[0]["tweet_id"] == "t_high"


def test_get_unanalyzed_excludes_analyzed(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    _insert_tweet(conn, "t1", "alice", "big alpha", "standalone_text", 12.0, "testorg")
    conn.execute(
        "INSERT INTO viral_anatomies (org, tweet_id, author_handle, total_lift, format_bucket, anatomy_json, analyzed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        ("testorg", "t1", "alice", 12.0, "standalone_text", json.dumps(_SAMPLE_ANATOMY)),
    )
    conn.commit()

    results = db_mod.get_unanalyzed_viral_tweets("testorg", lift_threshold=10.0)
    assert results == []


def test_get_unanalyzed_respects_limit(monkeypatch):
    conn = _make_conn()
    import sable.pulse.meta.db as db_mod
    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    for i in range(5):
        _insert_tweet(conn, f"t{i}", "alice", f"post {i}", "standalone_text", 10.0 + i, "testorg")

    results = db_mod.get_unanalyzed_viral_tweets("testorg", lift_threshold=10.0, limit=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# analyze_viral_tweet
# ---------------------------------------------------------------------------

def test_analyze_viral_tweet_calls_claude_and_parses(monkeypatch):
    import sable.pulse.meta.anatomy as anatomy_mod

    monkeypatch.setattr(anatomy_mod, "call_claude_json", lambda prompt, **kw: json.dumps(_SAMPLE_ANATOMY))

    tweet = {"tweet_id": "t1", "text": "Big alpha drop incoming", "total_lift": 14.0,
             "author_handle": "alice", "format_bucket": "standalone_text"}
    result = anatomy_mod.analyze_viral_tweet(tweet, "testorg")

    assert isinstance(result, dict)
    for key in _SAMPLE_ANATOMY:
        assert key in result


def test_analyze_viral_tweet_propagates_error(monkeypatch):
    import sable.pulse.meta.anatomy as anatomy_mod

    def _raise(prompt, **kw):
        raise SableError("QUOTA", "quota exceeded")

    monkeypatch.setattr(anatomy_mod, "call_claude_json", _raise)

    tweet = {"tweet_id": "t1", "text": "text", "total_lift": 11.0,
             "author_handle": "alice", "format_bucket": "standalone_text"}
    with pytest.raises(SableError):
        anatomy_mod.analyze_viral_tweet(tweet, "testorg")


# ---------------------------------------------------------------------------
# run_anatomy_enrichment
# ---------------------------------------------------------------------------

def test_run_anatomy_enrichment_saves_and_returns_count(monkeypatch, tmp_path):
    import sable.pulse.meta.anatomy as anatomy_mod

    tweets = [
        {"tweet_id": "t1", "text": "post one", "total_lift": 12.0,
         "author_handle": "alice", "format_bucket": "standalone_text"},
        {"tweet_id": "t2", "text": "post two", "total_lift": 11.0,
         "author_handle": "bob", "format_bucket": "standalone_text"},
    ]
    monkeypatch.setattr(anatomy_mod, "get_unanalyzed_viral_tweets", lambda org, **kw: tweets)
    monkeypatch.setattr(anatomy_mod, "call_claude_json", lambda prompt, **kw: json.dumps(_SAMPLE_ANATOMY))

    saved_calls = []
    monkeypatch.setattr(anatomy_mod, "save_anatomy", lambda **kw: saved_calls.append(kw))

    count = anatomy_mod.run_anatomy_enrichment("testorg", vault_root=tmp_path)

    assert count == 2
    assert len(saved_calls) == 2


def test_run_enrichment_skips_failed_tweet(monkeypatch, tmp_path):
    import sable.pulse.meta.anatomy as anatomy_mod

    tweets = [
        {"tweet_id": "t1", "text": "good post", "total_lift": 12.0,
         "author_handle": "alice", "format_bucket": "standalone_text"},
        {"tweet_id": "t2", "text": "bad post", "total_lift": 11.0,
         "author_handle": "bob", "format_bucket": "standalone_text"},
    ]
    monkeypatch.setattr(anatomy_mod, "get_unanalyzed_viral_tweets", lambda org, **kw: tweets)

    call_count = [0]

    def _claude(prompt, **kw):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("network error")
        return json.dumps(_SAMPLE_ANATOMY)

    monkeypatch.setattr(anatomy_mod, "call_claude_json", _claude)
    monkeypatch.setattr(anatomy_mod, "save_anatomy", lambda **kw: None)

    count = anatomy_mod.run_anatomy_enrichment("testorg", vault_root=tmp_path)

    assert count == 1  # second tweet skipped, no exception raised


# ---------------------------------------------------------------------------
# ViralAnatomy + write_anatomy_vault_note
# ---------------------------------------------------------------------------

def _make_anatomy(**overrides):
    import sable.pulse.meta.anatomy as anatomy_mod
    defaults = dict(
        tweet_id="t_vault_1",
        author_handle="alice",
        total_lift=14.5,
        format_bucket="standalone_text",
        text="This will change everything.",
        hook_structure="bold claim",
        hook_length_words=5,
        first_sentence="This will change everything.",
        emotional_register="excited",
        topic_cluster="DeFi yields",
        has_cta=False,
        cta_type=None,
        retweet_bait=True,
        retweet_bait_element="controversial prediction",
        is_thread=False,
        thread_length=None,
        analyzed_at="2026-03-25T00:00:00+00:00",
    )
    defaults.update(overrides)
    return anatomy_mod.ViralAnatomy(**defaults)


def test_zero_viral_tweets_graceful(monkeypatch, tmp_path):
    import sable.pulse.meta.anatomy as anatomy_mod
    monkeypatch.setattr(anatomy_mod, "get_unanalyzed_viral_tweets", lambda org, **kw: [])
    count = anatomy_mod.run_anatomy_enrichment("testorg", vault_root=tmp_path)
    assert count == 0


def test_max_per_run_cap(monkeypatch, tmp_path):
    import sable.pulse.meta.anatomy as anatomy_mod

    captured = {}

    def _get_tweets(org, lift_threshold, limit):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(anatomy_mod, "get_unanalyzed_viral_tweets", _get_tweets)
    anatomy_mod.run_anatomy_enrichment("testorg", vault_root=tmp_path, max_per_run=5)
    assert captured["limit"] == 5


def test_vault_note_written(tmp_path):
    import sable.pulse.meta.anatomy as anatomy_mod
    va = _make_anatomy()
    path = anatomy_mod.write_anatomy_vault_note(va, tmp_path)
    assert path.exists()
    assert path == tmp_path / "content" / "viral_anatomy" / "t_vault_1.md"
    import yaml
    content = path.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["type"] == "viral_anatomy"
    assert fm["lift"] == 14.5
    assert fm["format"] == "standalone_text"
    assert fm["hook_structure"] == "bold claim"


def test_vault_note_body_contains_tweet_text(tmp_path):
    import sable.pulse.meta.anatomy as anatomy_mod
    va = _make_anatomy(text="Alpha is leaking early.")
    anatomy_mod.write_anatomy_vault_note(va, tmp_path)
    content = (tmp_path / "content" / "viral_anatomy" / "t_vault_1.md").read_text(encoding="utf-8")
    assert "Alpha is leaking early." in content


def test_run_enrichment_writes_vault_note(monkeypatch, tmp_path):
    import sable.pulse.meta.anatomy as anatomy_mod

    tweets = [
        {"tweet_id": "t_note", "text": "Big alpha drop", "total_lift": 15.0,
         "author_handle": "alice", "format_bucket": "standalone_text"},
    ]
    monkeypatch.setattr(anatomy_mod, "get_unanalyzed_viral_tweets", lambda org, **kw: tweets)
    monkeypatch.setattr(anatomy_mod, "call_claude_json", lambda prompt, **kw: json.dumps(_SAMPLE_ANATOMY))
    monkeypatch.setattr(anatomy_mod, "save_anatomy", lambda **kw: None)

    anatomy_mod.run_anatomy_enrichment("testorg", vault_root=tmp_path)

    note_path = tmp_path / "content" / "viral_anatomy" / "t_note.md"
    assert note_path.exists()
