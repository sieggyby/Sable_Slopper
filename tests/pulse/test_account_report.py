"""Tests for sable/pulse/account_report.py — Slice A+B+C: data model, readers, helpers, niche integration, CLI."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sable.pulse.account_report import (
    AccountFormatReport,
    FormatLiftEntry,
    _classify_post,
    _compute_account_baseline,
    _divergence_signal,
    _engagement_score,
    compute_account_format_lift,
    render_account_report,
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_PULSE_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    account_handle TEXT NOT NULL,
    platform TEXT DEFAULT 'twitter',
    url TEXT,
    text TEXT,
    posted_at TEXT,
    sable_content_type TEXT,
    sable_content_path TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    taken_at TEXT DEFAULT (datetime('now')),
    likes INTEGER DEFAULT 0,
    retweets INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    bookmarks INTEGER DEFAULT 0,
    quotes INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS account_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_handle TEXT NOT NULL,
    taken_at TEXT DEFAULT (datetime('now')),
    followers INTEGER DEFAULT 0,
    following INTEGER DEFAULT 0,
    tweet_count INTEGER DEFAULT 0
);
"""


def _make_pulse_db(tmp_path: Path) -> Path:
    path = tmp_path / "pulse.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_PULSE_SCHEMA)
    conn.commit()
    conn.close()
    return path


def _recent_iso(days_ago: int = 1) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def _insert_post(conn: sqlite3.Connection, post_id: str, handle: str,
                 ct: str = "text", days_ago: int = 1) -> None:
    conn.execute(
        """INSERT INTO posts (id, account_handle, text, posted_at, sable_content_type)
           VALUES (?, ?, ?, ?, ?)""",
        (post_id, handle, f"text of {post_id}", _recent_iso(days_ago), ct),
    )


def _insert_snapshot(conn: sqlite3.Connection, post_id: str,
                     likes: int = 0, retweets: int = 0, replies: int = 0,
                     views: int = 0, bookmarks: int = 0, quotes: int = 0) -> None:
    conn.execute(
        """INSERT INTO snapshots (post_id, likes, retweets, replies, views, bookmarks, quotes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (post_id, likes, retweets, replies, views, bookmarks, quotes),
    )


# ---------------------------------------------------------------------------
# _classify_post
# ---------------------------------------------------------------------------

def test_classify_post_clip_maps_to_short_clip():
    assert _classify_post({"sable_content_type": "clip"}) == "short_clip"


def test_classify_post_meme_maps_to_single_image():
    assert _classify_post({"sable_content_type": "meme"}) == "single_image"


def test_classify_post_explainer_maps_to_long_clip():
    assert _classify_post({"sable_content_type": "explainer"}) == "long_clip"


def test_classify_post_faceswap_maps_to_short_clip():
    assert _classify_post({"sable_content_type": "faceswap"}) == "short_clip"


def test_classify_post_text_type_delegates_to_classify_format():
    # text type with no media → standalone_text
    result = _classify_post({"sable_content_type": "text", "text": "hello world"})
    assert result == "standalone_text"


def test_classify_post_unknown_type_returns_valid_bucket():
    from sable.pulse.meta.fingerprint import FORMAT_BUCKETS
    result = _classify_post({"sable_content_type": "unknown", "text": ""})
    assert result in FORMAT_BUCKETS


def test_classify_post_missing_type_returns_valid_bucket():
    from sable.pulse.meta.fingerprint import FORMAT_BUCKETS
    result = _classify_post({})
    assert result in FORMAT_BUCKETS


# ---------------------------------------------------------------------------
# _compute_account_baseline
# ---------------------------------------------------------------------------

def test_compute_baseline_returns_floor_for_empty_posts():
    assert _compute_account_baseline([]) == 1.0


def test_compute_baseline_returns_at_least_one():
    # All posts with zero engagement → floor 1.0
    posts = [{"likes": 0, "retweets": 0, "replies": 0, "views": 0, "bookmarks": 0, "quotes": 0}]
    assert _compute_account_baseline(posts) == 1.0


def test_compute_baseline_uses_median():
    # Median of [10, 20, 30] = 20 → engagement for each post
    # engagement_score for post with likes=10 → 10
    posts = [
        {"likes": 10, "retweets": 0, "replies": 0, "views": 0, "bookmarks": 0, "quotes": 0},
        {"likes": 20, "retweets": 0, "replies": 0, "views": 0, "bookmarks": 0, "quotes": 0},
        {"likes": 30, "retweets": 0, "replies": 0, "views": 0, "bookmarks": 0, "quotes": 0},
    ]
    result = _compute_account_baseline(posts)
    assert result == 20.0


# ---------------------------------------------------------------------------
# _engagement_score
# ---------------------------------------------------------------------------

def test_engagement_score_formula():
    row = {"likes": 10, "retweets": 2, "replies": 3, "views": 100, "bookmarks": 5, "quotes": 1}
    # 10 + 3*3 + 4*2 + 5*1 + 2*5 + 0.5*100 = 10+9+8+5+10+50 = 92
    assert _engagement_score(row) == 92.0


def test_engagement_score_none_values_treated_as_zero():
    row = {"likes": None, "retweets": None, "replies": None, "views": None, "bookmarks": None, "quotes": None}
    assert _engagement_score(row) == 0.0


def test_engagement_score_missing_keys_treated_as_zero():
    assert _engagement_score({}) == 0.0


# ---------------------------------------------------------------------------
# _divergence_signal
# ---------------------------------------------------------------------------

def test_divergence_double_down():
    assert _divergence_signal(2.0, 2.0) == "DOUBLE DOWN"


def test_divergence_execution_gap():
    assert _divergence_signal(0.7, 2.0) == "EXECUTION GAP"


def test_divergence_account_differentiation():
    assert _divergence_signal(2.0, 0.5) == "ACCOUNT DIFFERENTIATION"


def test_divergence_avoid():
    assert _divergence_signal(0.5, 0.5) == "AVOID"


def test_divergence_neutral_mid_range():
    assert _divergence_signal(1.2, 1.2) == "NEUTRAL"


def test_divergence_none_account_lift():
    assert _divergence_signal(None, 2.0) == "NEUTRAL"


def test_divergence_none_niche_lift():
    assert _divergence_signal(2.0, None) == "NEUTRAL"


# ---------------------------------------------------------------------------
# compute_account_format_lift — empty pulse.db
# ---------------------------------------------------------------------------

def test_empty_pulse_db_returns_zero_posts(tmp_path):
    db = _make_pulse_db(tmp_path)
    report = compute_account_format_lift("alice", "testorg", 30, db)
    assert report.total_posts == 0
    assert report.entries == []
    assert report.missing_niche_formats == []


def test_empty_pulse_db_no_exception_on_bare_handle(tmp_path):
    """Bare handle (no @) is normalized without raising."""
    db = _make_pulse_db(tmp_path)
    report = compute_account_format_lift("alice", "", 30, db)
    assert report.handle == "@alice"
    assert report.total_posts == 0


# ---------------------------------------------------------------------------
# compute_account_format_lift — posts without snapshots
# ---------------------------------------------------------------------------

def test_posts_without_snapshots_treated_as_zero_engagement(tmp_path):
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _insert_post(conn, "p1", "@alice", "text")
    _insert_post(conn, "p2", "@alice", "text")
    conn.commit()
    conn.close()

    report = compute_account_format_lift("alice", "", 30, db)
    assert report.total_posts == 2
    # Both posts are standalone_text, 2 posts, engagement=0 each
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.format_bucket == "standalone_text"
    assert entry.post_count == 2
    # engagement 0 / baseline 1.0 = 0.0
    assert entry.account_lift == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_account_format_lift — minimum data guard
# ---------------------------------------------------------------------------

def test_single_post_in_bucket_has_none_lift(tmp_path):
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _insert_post(conn, "c1", "@alice", "clip")  # → short_clip (1 post only)
    _insert_post(conn, "t1", "@alice", "text")
    _insert_post(conn, "t2", "@alice", "text")
    conn.commit()
    conn.close()

    report = compute_account_format_lift("alice", "", 30, db)
    buckets = {e.format_bucket: e for e in report.entries}

    # short_clip has only 1 post → None lift
    assert buckets["short_clip"].account_lift is None
    assert buckets["short_clip"].post_count == 1
    assert buckets["short_clip"].divergence_signal == "NEUTRAL"

    # standalone_text has 2 posts → lift computed
    assert buckets["standalone_text"].account_lift is not None
    assert buckets["standalone_text"].post_count == 2


# ---------------------------------------------------------------------------
# compute_account_format_lift — correct lift computation
# ---------------------------------------------------------------------------

def test_lift_computed_correctly_for_two_posts(tmp_path):
    """Two standalone_text posts with known engagement produce correct lift."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _insert_post(conn, "t1", "@alice", "text")
    _insert_snapshot(conn, "t1", likes=20)   # score = 20
    _insert_post(conn, "t2", "@alice", "text")
    _insert_snapshot(conn, "t2", likes=40)   # score = 40
    conn.commit()
    conn.close()

    report = compute_account_format_lift("alice", "", 30, db)
    assert len(report.entries) == 1
    entry = report.entries[0]
    # baseline = median([20, 40]) = 30
    # mean score = (20 + 40) / 2 = 30
    # lift = 30 / 30 = 1.0
    assert entry.account_lift == pytest.approx(1.0)


def test_lift_reflects_format_divergence(tmp_path):
    """Clips perform better than text for this account."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    # 3 text posts with low engagement
    for i in range(3):
        _insert_post(conn, f"t{i}", "@alice", "text")
        _insert_snapshot(conn, f"t{i}", likes=10)
    # 3 clip posts with high engagement
    for i in range(3):
        _insert_post(conn, f"c{i}", "@alice", "clip")
        _insert_snapshot(conn, f"c{i}", likes=100)
    conn.commit()
    conn.close()

    report = compute_account_format_lift("alice", "", 30, db)
    buckets = {e.format_bucket: e for e in report.entries}
    assert buckets["short_clip"].account_lift > buckets["standalone_text"].account_lift


# ---------------------------------------------------------------------------
# compute_account_format_lift — handle normalization
# ---------------------------------------------------------------------------

def test_at_handle_in_db_found_by_bare_handle_query(tmp_path):
    """Posts stored as @alice are returned when querying with bare 'alice'."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _insert_post(conn, "p1", "@alice", "text")
    _insert_post(conn, "p2", "@alice", "text")
    conn.commit()
    conn.close()

    report = compute_account_format_lift("alice", "", 30, db)
    assert report.total_posts == 2


def test_at_handle_in_db_found_by_at_handle_query(tmp_path):
    """Posts stored as @alice are returned when querying with '@alice'."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _insert_post(conn, "p1", "@alice", "text")
    _insert_post(conn, "p2", "@alice", "text")
    conn.commit()
    conn.close()

    report = compute_account_format_lift("@alice", "", 30, db)
    assert report.total_posts == 2


# ---------------------------------------------------------------------------
# compute_account_format_lift — days window
# ---------------------------------------------------------------------------

def test_posts_outside_window_excluded(tmp_path):
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _insert_post(conn, "recent", "@alice", "text", days_ago=5)
    _insert_post(conn, "old", "@alice", "text", days_ago=40)  # beyond 30d window
    conn.commit()
    conn.close()

    report = compute_account_format_lift("alice", "", days=30, pulse_db_path=db)
    assert report.total_posts == 1


# ---------------------------------------------------------------------------
# compute_account_format_lift — org fallback (no org → skip divergence)
# ---------------------------------------------------------------------------

def test_no_org_skips_divergence_analysis(tmp_path):
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _insert_post(conn, "t1", "@alice", "text")
    _insert_post(conn, "t2", "@alice", "text")
    conn.commit()
    conn.close()

    report = compute_account_format_lift("alice", "", 30, db)
    assert report.org == ""
    for entry in report.entries:
        assert entry.niche_lift is None
        assert entry.niche_trend_status is None
        assert entry.niche_confidence is None


def test_org_fallback_renders_without_exception(tmp_path):
    """When org is omitted, report renders account-only output cleanly."""
    db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _insert_post(conn, "t1", "@alice", "text")
    _insert_post(conn, "t2", "@alice", "text")
    _insert_snapshot(conn, "t1", likes=50)
    _insert_snapshot(conn, "t2", likes=30)
    conn.commit()
    conn.close()

    report = compute_account_format_lift("alice", "", 30, db)
    rendered = render_account_report(report)
    assert "@alice" in rendered
    assert "standalone_text" in rendered
    # No niche data → no "niche:" label in output
    assert "niche:" not in rendered


# ---------------------------------------------------------------------------
# render_account_report
# ---------------------------------------------------------------------------

def test_render_includes_handle():
    report = AccountFormatReport(
        handle="@alice",
        org="testorg",
        days=30,
        total_posts=5,
        entries=[],
        missing_niche_formats=[],
        generated_at="2026-03-24T00:00:00+00:00",
    )
    rendered = render_account_report(report)
    assert "@alice" in rendered


def test_render_includes_insufficient_data_label():
    entry = FormatLiftEntry(
        format_bucket="quote_tweet",
        account_lift=None,
        niche_lift=None,
        niche_trend_status=None,
        niche_confidence=None,
        post_count=1,
        divergence_signal="NEUTRAL",
    )
    report = AccountFormatReport(
        handle="@alice",
        org="",
        days=30,
        total_posts=1,
        entries=[entry],
        missing_niche_formats=[],
        generated_at="2026-03-24T00:00:00+00:00",
    )
    rendered = render_account_report(report)
    assert "insufficient data" in rendered
    assert "quote_tweet" in rendered


def test_render_shows_divergence_signal_when_niche_data_present():
    entry = FormatLiftEntry(
        format_bucket="standalone_text",
        account_lift=2.0,
        niche_lift=2.0,
        niche_trend_status="rising",
        niche_confidence="high",
        post_count=5,
        divergence_signal="DOUBLE DOWN",
    )
    report = AccountFormatReport(
        handle="@alice",
        org="testorg",
        days=30,
        total_posts=5,
        entries=[entry],
        missing_niche_formats=[],
        generated_at="2026-03-24T00:00:00+00:00",
    )
    rendered = render_account_report(report)
    assert "DOUBLE DOWN" in rendered
    assert "niche:" in rendered


def test_render_shows_missing_niche_formats():
    report = AccountFormatReport(
        handle="@alice",
        org="testorg",
        days=30,
        total_posts=4,
        entries=[],
        missing_niche_formats=["long_clip", "thread"],
        generated_at="2026-03-24T00:00:00+00:00",
    )
    rendered = render_account_report(report)
    assert "long_clip" in rendered
    assert "thread" in rendered


# ---------------------------------------------------------------------------
# Meta.db schema helpers
# ---------------------------------------------------------------------------

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS scanned_tweets (
    tweet_id TEXT PRIMARY KEY,
    author_handle TEXT NOT NULL,
    text TEXT DEFAULT '',
    posted_at TEXT,
    format_bucket TEXT,
    attributes_json TEXT DEFAULT '[]',
    likes INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0,
    quotes INTEGER DEFAULT 0,
    bookmarks INTEGER DEFAULT 0,
    video_views INTEGER DEFAULT 0,
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
    format_lift_reliable INTEGER DEFAULT 0,
    author_quality_grade TEXT DEFAULT 'adequate',
    author_quality_weight REAL DEFAULT 0.75,
    scan_id INTEGER,
    org TEXT
);
"""


def _make_meta_db(tmp_path: Path) -> Path:
    path = tmp_path / "meta.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_META_SCHEMA)
    conn.commit()
    conn.close()
    return path


def _insert_meta_tweet(conn: sqlite3.Connection, tweet_id: str, author: str,
                       bucket: str, org: str, total_lift: float = 1.5,
                       days_ago: int = 5) -> None:
    conn.execute(
        """INSERT INTO scanned_tweets
           (tweet_id, author_handle, format_bucket, org, total_lift,
            author_quality_grade, author_quality_weight, posted_at)
           VALUES (?, ?, ?, ?, ?, 'adequate', 0.75, ?)""",
        (tweet_id, author, bucket, org, total_lift, _recent_iso(days_ago)),
    )


# ---------------------------------------------------------------------------
# _load_niche_lifts — meta.db integration tests
# ---------------------------------------------------------------------------

def test_niche_lift_loaded_from_meta_db(tmp_path):
    """4 scanned_tweets with total_lift=2.0 → niche_lift is not None and ≈ 2.0."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    # Insert 2 account posts so entry is created
    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    _insert_post(pconn, "ap1", "@alice", "text")
    _insert_post(pconn, "ap2", "@alice", "text")
    _insert_snapshot(pconn, "ap1", likes=10)
    _insert_snapshot(pconn, "ap2", likes=10)
    pconn.commit()
    pconn.close()

    # Insert 4 niche tweets (2 authors) for standalone_text
    mconn = sqlite3.connect(str(meta_db))
    _insert_meta_tweet(mconn, "m1", "@user1", "standalone_text", "testorg", total_lift=2.0)
    _insert_meta_tweet(mconn, "m2", "@user1", "standalone_text", "testorg", total_lift=2.0)
    _insert_meta_tweet(mconn, "m3", "@user2", "standalone_text", "testorg", total_lift=2.0)
    _insert_meta_tweet(mconn, "m4", "@user2", "standalone_text", "testorg", total_lift=2.0)
    mconn.commit()
    mconn.close()

    report = compute_account_format_lift("alice", "testorg", 30, pulse_db, meta_db)
    buckets = {e.format_bucket: e for e in report.entries}
    assert "standalone_text" in buckets
    entry = buckets["standalone_text"]
    assert entry.niche_lift is not None
    assert entry.niche_lift == pytest.approx(2.0, abs=0.1)


def test_divergence_execution_gap_with_niche_data(tmp_path):
    """Account clip (short_clip) with very low engagement + niche short_clip total_lift=1.7 → EXECUTION GAP."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    # Account posts: clip type (→ short_clip), very low engagement (score=0)
    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    for i in range(3):
        _insert_post(pconn, f"cp{i}", "@alice", "clip")
        _insert_snapshot(pconn, f"cp{i}", likes=0)
    # Add other posts to raise baseline so clips have low relative lift
    for i in range(3):
        _insert_post(pconn, f"tp{i}", "@alice", "text")
        _insert_snapshot(pconn, f"tp{i}", likes=1000)
    pconn.commit()
    pconn.close()

    # Niche: short_clip with high lift
    mconn = sqlite3.connect(str(meta_db))
    for i in range(4):
        _insert_meta_tweet(mconn, f"nm{i}", f"@nuser{i % 2}", "short_clip", "testorg", total_lift=1.7)
    mconn.commit()
    mconn.close()

    report = compute_account_format_lift("alice", "testorg", 30, pulse_db, meta_db)
    buckets = {e.format_bucket: e for e in report.entries}
    assert "short_clip" in buckets
    entry = buckets["short_clip"]
    assert entry.divergence_signal == "EXECUTION GAP"


def test_divergence_double_down_with_niche_data(tmp_path):
    """Account standalone_text with high engagement + niche total_lift=2.0 → DOUBLE DOWN."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    # Account: standalone_text posts with high engagement relative to baseline
    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    for i in range(3):
        _insert_post(pconn, f"t{i}", "@alice", "text")
        _insert_snapshot(pconn, f"t{i}", likes=1000)
    # Low-engagement posts for other type to keep baseline low
    for i in range(3):
        _insert_post(pconn, f"c{i}", "@alice", "clip")
        _insert_snapshot(pconn, f"c{i}", likes=1)
    pconn.commit()
    pconn.close()

    # Niche: standalone_text with high lift
    mconn = sqlite3.connect(str(meta_db))
    for i in range(4):
        _insert_meta_tweet(mconn, f"nm{i}", f"@nuser{i % 2}", "standalone_text", "testorg", total_lift=2.0)
    mconn.commit()
    mconn.close()

    report = compute_account_format_lift("alice", "testorg", 30, pulse_db, meta_db)
    buckets = {e.format_bucket: e for e in report.entries}
    assert "standalone_text" in buckets
    entry = buckets["standalone_text"]
    assert entry.divergence_signal == "DOUBLE DOWN"


def test_missing_niche_formats_detected_via_meta_db(tmp_path):
    """Niche has surging long_clip but account has none → long_clip in missing_niche_formats."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    # Account only has text posts
    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    _insert_post(pconn, "t1", "@alice", "text")
    _insert_post(pconn, "t2", "@alice", "text")
    pconn.commit()
    pconn.close()

    # Niche: long_clip surging
    mconn = sqlite3.connect(str(meta_db))
    for i in range(4):
        _insert_meta_tweet(mconn, f"lc{i}", f"@nuser{i % 2}", "long_clip", "testorg", total_lift=2.0)
    mconn.commit()
    mconn.close()

    report = compute_account_format_lift("alice", "testorg", 30, pulse_db, meta_db)
    assert "long_clip" in report.missing_niche_formats


def test_nonexistent_meta_db_path_skips_gracefully(tmp_path):
    """Nonexistent meta_db_path → no exception, niche_lift=None for all entries."""
    pulse_db = _make_pulse_db(tmp_path)

    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    _insert_post(pconn, "t1", "@alice", "text")
    _insert_post(pconn, "t2", "@alice", "text")
    _insert_snapshot(pconn, "t1", likes=20)
    _insert_snapshot(pconn, "t2", likes=20)
    pconn.commit()
    pconn.close()

    nonexistent = tmp_path / "does_not_exist.db"
    report = compute_account_format_lift("alice", "testorg", 30, pulse_db, nonexistent)
    for entry in report.entries:
        assert entry.niche_lift is None


def test_niche_tweets_outside_days_window_excluded(tmp_path):
    """Tweets older than the days window are not included in niche lift."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    _insert_post(pconn, "t1", "@alice", "text")
    _insert_post(pconn, "t2", "@alice", "text")
    pconn.commit()
    pconn.close()

    # Only old tweets in meta.db (outside the 7-day window we'll request)
    mconn = sqlite3.connect(str(meta_db))
    for i in range(4):
        _insert_meta_tweet(mconn, f"old{i}", f"@nuser{i%2}", "standalone_text",
                           "testorg", total_lift=2.0, days_ago=10)
    mconn.commit()
    mconn.close()

    # days=7 → only last 7 days; all meta tweets are 10 days old → excluded
    report = compute_account_format_lift("alice", "testorg", 7, pulse_db, meta_db)
    buckets = {e.format_bucket: e for e in report.entries}
    assert buckets["standalone_text"].niche_lift is None


def test_niche_confidence_is_C_when_loaded(tmp_path):
    """niche_confidence is 'C' when niche data is loaded (quality gates always fail
    with no baselines)."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    _insert_post(pconn, "t1", "@alice", "text")
    _insert_post(pconn, "t2", "@alice", "text")
    pconn.commit()
    pconn.close()

    mconn = sqlite3.connect(str(meta_db))
    for i in range(4):
        _insert_meta_tweet(mconn, f"m{i}", f"@nuser{i%2}", "standalone_text",
                           "testorg", total_lift=2.0)
    mconn.commit()
    mconn.close()

    report = compute_account_format_lift("alice", "testorg", 30, pulse_db, meta_db)
    buckets = {e.format_bucket: e for e in report.entries}
    entry = buckets["standalone_text"]
    assert entry.niche_lift is not None
    assert entry.niche_confidence == "C"


def test_niche_org_mismatch_returns_no_niche_data(tmp_path):
    """meta.db tweets for a different org are excluded → niche_lift is None."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    _insert_post(pconn, "t1", "@alice", "text")
    _insert_post(pconn, "t2", "@alice", "text")
    pconn.commit()
    pconn.close()

    # Tweets for "other_org", not "testorg"
    mconn = sqlite3.connect(str(meta_db))
    for i in range(4):
        _insert_meta_tweet(mconn, f"m{i}", f"@nuser{i%2}", "standalone_text",
                           "other_org", total_lift=2.0)
    mconn.commit()
    mconn.close()

    report = compute_account_format_lift("alice", "testorg", 30, pulse_db, meta_db)
    for entry in report.entries:
        assert entry.niche_lift is None


def test_niche_confidence_populated_with_niche_data(tmp_path):
    """niche_confidence should be a non-None string when niche data exists."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    for i in range(3):
        _insert_post(pconn, f"t{i}", "@alice", "text")
        _insert_snapshot(pconn, f"t{i}", likes=10)
    pconn.commit()
    pconn.close()

    mconn = sqlite3.connect(str(meta_db))
    for i in range(4):
        _insert_meta_tweet(mconn, f"m{i}", f"@nuser{i % 2}", "standalone_text",
                           "testorg", total_lift=1.5)
    mconn.commit()
    mconn.close()

    report = compute_account_format_lift("alice", "testorg", 30, pulse_db, meta_db)
    buckets = {e.format_bucket: e for e in report.entries}
    assert "standalone_text" in buckets
    entry = buckets["standalone_text"]
    assert entry.niche_confidence is not None, "niche_confidence should be set when niche data exists"


def test_empty_scanned_tweets_after_org_filter(tmp_path):
    """When meta.db has tweets but none match the org, niche data is empty."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    pconn = sqlite3.connect(str(pulse_db))
    pconn.row_factory = sqlite3.Row
    for i in range(3):
        _insert_post(pconn, f"t{i}", "@alice", "clip")
        _insert_snapshot(pconn, f"t{i}", likes=20)
    pconn.commit()
    pconn.close()

    # Insert tweets for a completely different org
    mconn = sqlite3.connect(str(meta_db))
    for i in range(5):
        _insert_meta_tweet(mconn, f"m{i}", f"@nuser{i % 2}", "short_clip",
                           "wrong_org", total_lift=3.0)
    mconn.commit()
    mconn.close()

    report = compute_account_format_lift("alice", "testorg", 30, pulse_db, meta_db)
    buckets = {e.format_bucket: e for e in report.entries}
    assert "short_clip" in buckets
    entry = buckets["short_clip"]
    assert entry.niche_lift is None, "niche_lift should be None when no tweets match the org"
    assert entry.niche_confidence is None
