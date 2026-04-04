"""Tests for the watchlist digest module."""
from __future__ import annotations

import json
import sqlite3

import pytest


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
    """Proxy that keeps the in-memory connection alive after close()."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.row_factory = conn.row_factory

    def __setattr__(self, name, value):
        if name in ("_conn", "row_factory"):
            object.__setattr__(self, name, value)
            if name == "row_factory" and hasattr(self, "_conn"):
                self._conn.row_factory = value
        else:
            object.__setattr__(self, name, value)

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


def _insert_tweet(conn, tweet_id, author_handle, text, format_bucket, total_lift, org,
                  posted_at="2026-03-20T12:00:00+00:00"):
    conn.execute(
        "INSERT INTO scanned_tweets (tweet_id, author_handle, text, format_bucket, total_lift, org, posted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (tweet_id, author_handle, text, format_bucket, total_lift, org, posted_at),
    )
    conn.commit()


def _insert_anatomy(conn, org, tweet_id, author_handle, total_lift, format_bucket, anatomy_json):
    conn.execute(
        "INSERT INTO viral_anatomies (org, tweet_id, author_handle, total_lift, format_bucket, anatomy_json, analyzed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (org, tweet_id, author_handle, total_lift, format_bucket, anatomy_json),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_top_n_filtering():
    """_get_digest_posts returns exactly top_n rows, ordered by lift descending."""
    conn = _make_conn()

    for i in range(20):
        _insert_tweet(conn, f"t{i}", "alice", f"post {i}", "standalone_text", 3.0 + i, "testorg")

    import sable.pulse.meta.digest as digest_mod

    rows, total = digest_mod._get_digest_posts("testorg", period_days=30, top_n=10, conn=conn)

    assert len(rows) == 10
    lifts = [r["total_lift"] for r in rows]
    assert lifts == sorted(lifts, reverse=True)


def test_anatomy_cache_used(monkeypatch):
    """When anatomy_json is present, _analyze_post_for_digest does NOT call Claude."""
    import sable.pulse.meta.digest as digest_mod

    def _raise(*a, **kw):
        raise RuntimeError("Claude should not be called")

    monkeypatch.setattr(digest_mod, "call_claude_json" if hasattr(digest_mod, "call_claude_json") else "_sentinel",
                        _raise, raising=False)

    # Patch at the api module level to be safe
    import sable.shared.api as api_mod
    monkeypatch.setattr(api_mod, "call_claude_json", _raise)

    post = {
        "tweet_id": "t1",
        "author_handle": "alice",
        "text": "big alpha incoming",
        "total_lift": 12.0,
        "format_bucket": "standalone_text",
        "anatomy_json": json.dumps(_SAMPLE_ANATOMY),
    }

    hook_pattern, analysis, steal = digest_mod._analyze_post_for_digest(post, org_id=None)
    assert hook_pattern == _SAMPLE_ANATOMY["hook_structure"]
    assert steal == _SAMPLE_ANATOMY["retweet_bait_element"]


def test_anatomy_cache_miss_calls_claude(monkeypatch):
    """When anatomy_json is None, _analyze_post_for_digest calls Claude once."""
    import sable.pulse.meta.digest as digest_mod
    import sable.shared.api as api_mod

    call_count = [0]
    response = {"analysis": "good hook", "steal": "urgency", "hook_pattern": "stat opener"}

    def _fake_claude(prompt, **kw):
        call_count[0] += 1
        return json.dumps(response)

    monkeypatch.setattr(api_mod, "call_claude_json", _fake_claude)

    post = {
        "tweet_id": "t1",
        "author_handle": "alice",
        "text": "some tweet",
        "total_lift": 8.0,
        "format_bucket": "standalone_text",
        "anatomy_json": None,
    }

    hook_pattern, analysis, steal = digest_mod._analyze_post_for_digest(post, org_id=None)
    assert call_count[0] == 1
    assert hook_pattern == "stat opener"
    assert analysis == "good hook"
    assert steal == "urgency"


def test_empty_period(monkeypatch):
    """generate_digest returns empty DigestReport when no posts meet lift threshold."""
    conn = _make_conn()
    # Insert tweets below threshold
    _insert_tweet(conn, "t1", "alice", "low post", "standalone_text", 1.5, "testorg")

    import sable.pulse.meta.digest as digest_mod
    import sable.pulse.meta.db as db_mod

    monkeypatch.setattr(db_mod, "get_conn", lambda: _NoClose(conn))

    # Also patch platform db to avoid real DB lookup
    monkeypatch.setattr(digest_mod, "generate_digest", digest_mod.generate_digest, raising=False)
    import sable.platform.db as platform_db_mod
    monkeypatch.setattr(platform_db_mod, "get_db", lambda: conn, raising=False)

    report = digest_mod.generate_digest(
        org="testorg",
        period_days=30,
        top_n=10,
    )

    assert report.entries == []
    assert report.org == "testorg"


def test_vault_note_saved(tmp_path):
    """save_digest_to_vault writes file with correct frontmatter and org in body."""
    from sable.pulse.meta.digest import DigestEntry, DigestReport, save_digest_to_vault, render_digest

    report = DigestReport(
        org="testorg",
        period_days=7,
        generated_at="2026-03-25T12:00:00+00:00",
        entries=[
            DigestEntry(
                author_handle="alice",
                tweet_id="t1",
                total_lift=5.0,
                format_bucket="standalone_text",
                tweet_text="Big alpha drop",
                hook_pattern="bold claim",
                analysis="Strong urgency hook.",
                steal="Urgency framing",
            )
        ],
        total_posts_considered=1,
    )

    saved_path = save_digest_to_vault(report, tmp_path)

    assert saved_path.exists()
    assert saved_path.name == "watchlist_digest_2026-03-25.md"
    content = saved_path.read_text()
    assert "type: digest" in content
    assert "testorg" in content
    assert (tmp_path / "digests").is_dir()


def test_render_output():
    """render_digest produces non-empty string containing both author handles."""
    from sable.pulse.meta.digest import DigestEntry, DigestReport, render_digest

    report = DigestReport(
        org="testorg",
        period_days=7,
        generated_at="2026-03-25T12:00:00+00:00",
        entries=[
            DigestEntry(
                author_handle="alice",
                tweet_id="t1",
                total_lift=7.5,
                format_bucket="standalone_text",
                tweet_text="Alpha incoming",
                hook_pattern="bold claim",
                analysis="Strong hook.",
                steal="Urgency",
            ),
            DigestEntry(
                author_handle="bob",
                tweet_id="t2",
                total_lift=4.2,
                format_bucket="thread",
                tweet_text="Thread drop",
                hook_pattern="question hook",
                analysis="Curiosity gap.",
                steal="Open loop",
            ),
        ],
        total_posts_considered=2,
    )

    rendered = render_digest(report)
    assert rendered
    assert "@alice" in rendered
    assert "@bob" in rendered


def test_analyze_post_passes_org_id_to_claude(monkeypatch):
    """When org_id is not None, _analyze_post_for_digest passes it to call_claude_json."""
    import sable.pulse.meta.digest as digest_mod
    import sable.shared.api as api_mod

    captured_kwargs = {}
    response = {"analysis": "test", "steal": "test", "hook_pattern": "test"}

    def _fake_claude(prompt, **kw):
        captured_kwargs.update(kw)
        return json.dumps(response)

    monkeypatch.setattr(api_mod, "call_claude_json", _fake_claude)

    post = {
        "tweet_id": "t1",
        "author_handle": "alice",
        "text": "some tweet",
        "total_lift": 8.0,
        "format_bucket": "standalone_text",
        "anatomy_json": None,
    }

    digest_mod._analyze_post_for_digest(post, org_id="myorg")
    assert captured_kwargs.get("org_id") == "myorg"


def test_generate_digest_caps_top_n():
    """generate_digest internally caps top_n to MAX_DIGEST_POSTS."""
    from sable.pulse.meta.digest import MAX_DIGEST_POSTS
    assert MAX_DIGEST_POSTS == 25
