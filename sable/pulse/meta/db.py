"""SQLite schema and queries for pulse meta (meta.db)."""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from sable.shared.paths import meta_db_path

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS scanned_tweets (
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

CREATE TABLE IF NOT EXISTS author_profiles (
    author_handle TEXT NOT NULL,
    org TEXT NOT NULL,
    tweet_count INTEGER DEFAULT 0,
    last_seen TEXT,
    last_tweet_id TEXT,
    PRIMARY KEY (author_handle, org)
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    mode TEXT,
    tweets_collected INTEGER DEFAULT 0,
    tweets_new INTEGER DEFAULT 0,
    estimated_cost REAL,
    watchlist_size INTEGER DEFAULT 0,
    claude_raw TEXT
);

CREATE TABLE IF NOT EXISTS format_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    format_bucket TEXT NOT NULL,
    period_days INTEGER NOT NULL,
    avg_total_lift REAL,
    sample_count INTEGER,
    unique_authors INTEGER,
    computed_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topic_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    scan_id INTEGER,
    term TEXT NOT NULL,
    mention_count INTEGER DEFAULT 0,
    unique_authors INTEGER DEFAULT 0,
    avg_lift REAL,
    prev_scan_mentions INTEGER DEFAULT 0,
    acceleration REAL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_scanned_tweets_author ON scanned_tweets(author_handle);
CREATE INDEX IF NOT EXISTS idx_scanned_tweets_org ON scanned_tweets(org);
CREATE INDEX IF NOT EXISTS idx_scanned_tweets_bucket ON scanned_tweets(format_bucket);
CREATE INDEX IF NOT EXISTS idx_scanned_tweets_scan ON scanned_tweets(scan_id);
CREATE INDEX IF NOT EXISTS idx_format_baselines_org_bucket ON format_baselines(org, format_bucket);
CREATE INDEX IF NOT EXISTS idx_format_baselines_ts ON format_baselines (org, format_bucket, period_days, computed_at);
CREATE INDEX IF NOT EXISTS idx_topic_signals_org_scan ON topic_signals(org, scan_id);

CREATE TABLE IF NOT EXISTS hook_pattern_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    org         TEXT NOT NULL,
    format_bucket TEXT NOT NULL,
    patterns_json TEXT NOT NULL,
    generated_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hook_patterns_key
    ON hook_pattern_cache (org, format_bucket);

CREATE TABLE IF NOT EXISTS viral_anatomies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    org            TEXT NOT NULL,
    tweet_id       TEXT NOT NULL,
    author_handle  TEXT NOT NULL,
    total_lift     REAL NOT NULL,
    format_bucket  TEXT NOT NULL,
    anatomy_json   TEXT NOT NULL,
    analyzed_at    TEXT NOT NULL,
    UNIQUE(org, tweet_id)
);
CREATE INDEX IF NOT EXISTS idx_viral_anatomies_org
    ON viral_anatomies (org);
CREATE INDEX IF NOT EXISTS idx_viral_anatomies_org_bucket
    ON viral_anatomies (org, format_bucket);

CREATE TABLE IF NOT EXISTS lexicon_terms (
    org TEXT NOT NULL,
    term TEXT NOT NULL,
    category TEXT,
    gloss TEXT,
    lsr REAL,
    updated_at TEXT,
    UNIQUE(org, term)
);
CREATE INDEX IF NOT EXISTS idx_lexicon_terms_org ON lexicon_terms(org);

CREATE TABLE IF NOT EXISTS author_cadence (
    author_handle TEXT NOT NULL,
    org TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    posts_recent_half INTEGER,
    posts_prior_half INTEGER,
    median_lift_recent REAL,
    median_lift_prior REAL,
    vol_drop REAL,
    eng_drop REAL,
    fmt_reg REAL,
    silence_gradient REAL,
    insufficient_data TEXT,
    window_days INTEGER,
    UNIQUE(author_handle, org)
);
"""


def get_conn() -> sqlite3.Connection:
    path = meta_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def migrate() -> None:
    """Initialize or migrate the meta database."""
    conn = get_conn()
    conn.execute("DROP INDEX IF EXISTS idx_format_baselines_key")
    conn.commit()
    with conn:
        conn.executescript(_SCHEMA)
        version = conn.execute("SELECT version FROM schema_version").fetchone()
        if version is None:
            conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
    conn.close()


# ---------------------------------------------------------------------------
# Scan runs
# ---------------------------------------------------------------------------

def create_scan_run(org: str, mode: str, watchlist_size: int = 0) -> int:
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO scan_runs (org, mode, watchlist_size) VALUES (?, ?, ?)",
        (org, mode, watchlist_size),
    )
    assert cursor.lastrowid is not None
    scan_id: int = cursor.lastrowid
    conn.commit()
    conn.close()
    return scan_id


def complete_scan_run(scan_id: int, tweets_collected: int, tweets_new: int,
                      estimated_cost: float = 0.0, claude_raw: str = "") -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """UPDATE scan_runs
               SET completed_at = datetime('now'),
                   tweets_collected = ?,
                   tweets_new = ?,
                   estimated_cost = ?,
                   claude_raw = ?
               WHERE id = ?""",
            (tweets_collected, tweets_new, estimated_cost, claude_raw or None, scan_id),
        )
    conn.close()


def fail_scan_run(
    scan_id: int, error: str,
    tweets_collected: int = 0, tweets_new: int = 0, estimated_cost: float = 0.0
) -> None:
    """Mark a scan run as failed by completing it with FAILED: prefix in claude_raw."""
    from sable.platform.errors import redact_error
    complete_scan_run(scan_id, tweets_collected, tweets_new, estimated_cost,
                      claude_raw=f"FAILED: {redact_error(error)}")


def get_scan_runs(org: str, limit: int = 20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM scan_runs WHERE org = ? ORDER BY id DESC LIMIT ?",
        (org, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Scanned tweets
# ---------------------------------------------------------------------------

def upsert_tweet(tweet: dict) -> bool:
    """Insert a scanned tweet. Returns True if new, False if already exists."""
    conn = get_conn()
    existing = conn.execute(
        "SELECT tweet_id FROM scanned_tweets WHERE tweet_id = ?",
        (tweet["tweet_id"],),
    ).fetchone()
    if existing:
        conn.close()
        return False

    attrs = tweet.get("attributes", [])
    attrs_json = json.dumps(attrs) if isinstance(attrs, list) else attrs

    with conn:
        conn.execute(
            """INSERT INTO scanned_tweets (
                tweet_id, author_handle, text, posted_at, format_bucket, attributes_json,
                likes, replies, reposts, quotes, bookmarks, video_views, video_duration,
                is_quote_tweet, is_thread, thread_length, has_image, has_video, has_link,
                author_followers,
                author_median_likes, author_median_replies, author_median_reposts,
                author_median_quotes, author_median_total, author_median_same_format,
                likes_lift, replies_lift, reposts_lift, quotes_lift,
                total_lift, format_lift,
                author_quality_grade, author_quality_weight, format_lift_reliable,
                scan_id, org
            ) VALUES (
                :tweet_id, :author_handle, :text, :posted_at, :format_bucket, :attributes_json,
                :likes, :replies, :reposts, :quotes, :bookmarks, :video_views, :video_duration,
                :is_quote_tweet, :is_thread, :thread_length, :has_image, :has_video, :has_link,
                :author_followers,
                :author_median_likes, :author_median_replies, :author_median_reposts,
                :author_median_quotes, :author_median_total, :author_median_same_format,
                :likes_lift, :replies_lift, :reposts_lift, :quotes_lift,
                :total_lift, :format_lift,
                :author_quality_grade, :author_quality_weight, :format_lift_reliable,
                :scan_id, :org
            )""",
            {
                "tweet_id": tweet["tweet_id"],
                "author_handle": tweet["author_handle"],
                "text": tweet.get("text", ""),
                "posted_at": tweet.get("posted_at", ""),
                "format_bucket": tweet.get("format_bucket"),
                "attributes_json": attrs_json,
                "likes": tweet.get("likes", 0),
                "replies": tweet.get("replies", 0),
                "reposts": tweet.get("reposts", 0),
                "quotes": tweet.get("quotes", 0),
                "bookmarks": tweet.get("bookmarks", 0),
                "video_views": tweet.get("video_views", 0),
                "video_duration": tweet.get("video_duration"),
                "is_quote_tweet": int(tweet.get("is_quote_tweet", False)),
                "is_thread": int(tweet.get("is_thread", False)),
                "thread_length": tweet.get("thread_length", 1),
                "has_image": int(tweet.get("has_image", False)),
                "has_video": int(tweet.get("has_video", False)),
                "has_link": int(tweet.get("has_link", False)),
                "author_followers": tweet.get("author_followers", 0),
                "author_median_likes": tweet.get("author_median_likes"),
                "author_median_replies": tweet.get("author_median_replies"),
                "author_median_reposts": tweet.get("author_median_reposts"),
                "author_median_quotes": tweet.get("author_median_quotes"),
                "author_median_total": tweet.get("author_median_total"),
                "author_median_same_format": tweet.get("author_median_same_format"),
                "likes_lift": tweet.get("likes_lift"),
                "replies_lift": tweet.get("replies_lift"),
                "reposts_lift": tweet.get("reposts_lift"),
                "quotes_lift": tweet.get("quotes_lift"),
                "total_lift": tweet.get("total_lift"),
                "format_lift": tweet.get("format_lift"),
                "author_quality_grade": tweet.get("author_quality_grade"),
                "author_quality_weight": tweet.get("author_quality_weight"),
                "format_lift_reliable": int(tweet.get("format_lift_reliable", False)),
                "scan_id": tweet.get("scan_id"),
                "org": tweet.get("org", ""),
            },
        )
    conn.close()
    return True


def get_author_tweets(author_handle: str, org: str, limit: int = 200) -> list[dict]:
    """Get historical tweets for an author (for building normalization baselines)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM scanned_tweets
           WHERE author_handle = ? AND org = ?
           ORDER BY posted_at DESC LIMIT ?""",
        (author_handle, org, limit),
    ).fetchall()
    conn.close()
    return [_row_to_tweet(r) for r in rows]


def get_tweets_for_scan(scan_id: int, org: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM scanned_tweets WHERE scan_id = ? AND org = ?",
        (scan_id, org),
    ).fetchall()
    conn.close()
    return [_row_to_tweet(r) for r in rows]


def get_recent_tweets(org: str, hours: int = 48) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM scanned_tweets
           WHERE org = ?
           AND posted_at >= datetime('now', ? || ' hours')
           ORDER BY posted_at DESC""",
        (org, f"-{hours}"),
    ).fetchall()
    conn.close()
    return [_row_to_tweet(r) for r in rows]


def _row_to_tweet(row) -> dict:
    d = dict(row)
    attrs_json = d.get("attributes_json") or "[]"
    try:
        d["attributes"] = json.loads(attrs_json)
    except Exception:
        d["attributes"] = []
    d["is_quote_tweet"] = bool(d.get("is_quote_tweet", 0))
    d["is_thread"] = bool(d.get("is_thread", 0))
    d["has_image"] = bool(d.get("has_image", 0))
    d["has_video"] = bool(d.get("has_video", 0))
    d["has_link"] = bool(d.get("has_link", 0))
    d["format_lift_reliable"] = bool(d.get("format_lift_reliable", 0))
    return d


# ---------------------------------------------------------------------------
# Author profiles (cursors)
# ---------------------------------------------------------------------------

def get_author_profile(author_handle: str, org: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM author_profiles WHERE author_handle = ? AND org = ?",
        (author_handle, org),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_author_profile(author_handle: str, org: str, last_tweet_id: str,
                           tweet_count: int, last_seen: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """INSERT INTO author_profiles (author_handle, org, last_tweet_id, tweet_count, last_seen)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(author_handle, org) DO UPDATE SET
                   last_tweet_id = excluded.last_tweet_id,
                   tweet_count = excluded.tweet_count,
                   last_seen = excluded.last_seen""",
            (author_handle, org, last_tweet_id, tweet_count, last_seen),
        )
    conn.close()


# ---------------------------------------------------------------------------
# Format baselines
# ---------------------------------------------------------------------------

def upsert_format_baseline(org: str, format_bucket: str, period_days: int,
                            avg_total_lift: float, sample_count: int, unique_authors: int) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """INSERT INTO format_baselines
               (org, format_bucket, period_days, avg_total_lift, sample_count, unique_authors)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (org, format_bucket, period_days, avg_total_lift, sample_count, unique_authors),
        )
    conn.close()


def get_format_baselines_as_of(org: str, as_of: str, period_days: int = 7,
                                conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """Return the most-recent baseline row per format_bucket where computed_at <= as_of."""
    _conn = conn or get_conn()
    try:
        rows = _conn.execute(
            """SELECT f.*
               FROM format_baselines f
               WHERE f.org = ? AND f.period_days = ? AND f.computed_at <= ?
                 AND f.computed_at = (
                     SELECT MAX(f2.computed_at) FROM format_baselines f2
                     WHERE f2.org = f.org AND f2.format_bucket = f.format_bucket
                       AND f2.period_days = f.period_days AND f2.computed_at <= ?
                 )""",
            (org, period_days, as_of, as_of),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if conn is None:
            _conn.close()


def prune_format_baselines(org: str, keep_n: int = 90,
                            conn: Optional[sqlite3.Connection] = None) -> None:
    """Keep only the most-recent keep_n rows per (org, format_bucket, period_days)."""
    _conn = conn or get_conn()
    try:
        with _conn:
            _conn.execute(
                """DELETE FROM format_baselines
                   WHERE org = ? AND id NOT IN (
                       SELECT id FROM format_baselines f2
                       WHERE f2.org = format_baselines.org
                         AND f2.format_bucket = format_baselines.format_bucket
                         AND f2.period_days = format_baselines.period_days
                       ORDER BY f2.computed_at DESC
                       LIMIT ?
                   )""",
                (org, keep_n),
            )
    finally:
        if conn is None:
            _conn.close()


def get_format_baselines(org: str, format_bucket: str, period_days: int,
                          limit: int = 5) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM format_baselines
           WHERE org = ? AND format_bucket = ? AND period_days = ?
           ORDER BY computed_at DESC LIMIT ?""",
        (org, format_bucket, period_days, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tweets_since(org: str, days: int, format_bucket: Optional[str] = None) -> list[dict]:
    """Get tweets from last N days for baseline computation."""
    conn = get_conn()
    if format_bucket:
        rows = conn.execute(
            """SELECT * FROM scanned_tweets
               WHERE org = ?
               AND format_bucket = ?
               AND posted_at >= datetime('now', ? || ' days')
               AND total_lift IS NOT NULL""",
            (org, format_bucket, f"-{days}"),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM scanned_tweets
               WHERE org = ?
               AND posted_at >= datetime('now', ? || ' days')
               AND total_lift IS NOT NULL""",
            (org, f"-{days}"),
        ).fetchall()
    conn.close()
    return [_row_to_tweet(r) for r in rows]


def get_high_lift_tweets(
    org: str, format_bucket: str, lift_threshold: float = 2.5,
    days: int = 30, limit: int = 20,
) -> list[dict]:
    """Return top tweets by total_lift for org+format in last N days."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM scanned_tweets
           WHERE org = ? AND format_bucket = ?
             AND posted_at >= datetime('now', ? || ' days')
             AND total_lift IS NOT NULL AND total_lift >= ?
           ORDER BY total_lift DESC LIMIT ?""",
        (org, format_bucket, f"-{days}", lift_threshold, limit),
    ).fetchall()
    conn.close()
    return [_row_to_tweet(r) for r in rows]


def get_oldest_tweet_date(org: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute(
        "SELECT MIN(posted_at) as oldest FROM scanned_tweets WHERE org = ?",
        (org,),
    ).fetchone()
    conn.close()
    return row["oldest"] if row else None


# ---------------------------------------------------------------------------
# Topic signals
# ---------------------------------------------------------------------------

def insert_topic_signals(org: str, scan_id: int, signals: list[dict]) -> None:
    conn = get_conn()
    with conn:
        for sig in signals:
            conn.execute(
                """INSERT INTO topic_signals
                   (org, scan_id, term, mention_count, unique_authors, avg_lift,
                    prev_scan_mentions, acceleration)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (org, scan_id, sig["term"], sig["mention_count"],
                 sig["unique_authors"], sig.get("avg_lift", 0.0),
                 sig.get("prev_scan_mentions", 0), sig.get("acceleration", 0.0)),
            )
    conn.close()


# ---------------------------------------------------------------------------
# Hook pattern cache
# ---------------------------------------------------------------------------

def upsert_hook_patterns(org: str, format_bucket: str, patterns_json: str) -> None:
    """Store (or overwrite) cached hook patterns for an org+format pair."""
    conn = get_conn()
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO hook_pattern_cache
               (org, format_bucket, patterns_json, generated_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (org, format_bucket, patterns_json),
        )
    conn.close()


def get_hook_patterns_cache(org: str, format_bucket: str) -> dict | None:
    """Return the cached hook pattern row for org+format, or None if absent."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM hook_pattern_cache WHERE org = ? AND format_bucket = ?",
        (org, format_bucket),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_latest_successful_scan_at(org: str) -> str | None:
    """Return completed_at of the newest non-failed scan for org, or None."""
    conn = get_conn()
    row = conn.execute(
        """SELECT completed_at FROM scan_runs
           WHERE org = ?
             AND completed_at IS NOT NULL
             AND (claude_raw IS NULL OR claude_raw NOT LIKE 'FAILED:%')
           ORDER BY completed_at DESC
           LIMIT 1""",
        (org,),
    ).fetchone()
    conn.close()
    return row["completed_at"] if row else None


# ---------------------------------------------------------------------------
# Viral anatomies
# ---------------------------------------------------------------------------

def save_anatomy(
    org: str,
    tweet_id: str,
    author_handle: str,
    total_lift: float,
    format_bucket: str,
    anatomy_json: str,
) -> None:
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                """INSERT OR IGNORE INTO viral_anatomies
                   (org, tweet_id, author_handle, total_lift, format_bucket,
                    anatomy_json, analyzed_at)
                   VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                (org, tweet_id, author_handle, total_lift, format_bucket, anatomy_json),
            )
    finally:
        conn.close()


def get_viral_anatomies(
    org: str,
    format_bucket: str,
    min_lift: float = 2.5,
    limit: int = 5,
    days: int = 30,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    """Return top viral anatomy rows for org+format_bucket, sorted by total_lift desc.

    Returns dicts with: tweet_id, author_handle, total_lift, anatomy_json (raw string).
    """
    _conn = conn or get_conn()
    try:
        rows = _conn.execute(
            """SELECT tweet_id, author_handle, total_lift, anatomy_json
               FROM viral_anatomies
               WHERE org = ? AND format_bucket = ? AND total_lift >= ?
                 AND analyzed_at >= datetime('now', ? || ' days')
               ORDER BY total_lift DESC
               LIMIT ?""",
            (org, format_bucket, min_lift, f"-{days}", limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if conn is None:
            _conn.close()


def get_unanalyzed_viral_tweets(
    org: str,
    lift_threshold: float = 10.0,
    limit: int = 20,
) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT st.tweet_id, st.author_handle, st.text,
                      st.format_bucket, st.total_lift
               FROM scanned_tweets st
               LEFT JOIN viral_anatomies va
                      ON va.org = st.org AND va.tweet_id = st.tweet_id
               WHERE st.org = ? AND st.total_lift >= ? AND va.id IS NULL
               ORDER BY st.total_lift DESC
               LIMIT ?""",
            (org, lift_threshold, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_top_topic_signals(
    org: str,
    limit: int = 20,
    min_unique_authors: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    """Return top topic signals from the latest successful scan for org.

    Returns a list of dicts with keys:
    term, avg_lift, acceleration, unique_authors, mention_count
    Sorted by (avg_lift * acceleration * unique_authors) descending.
    """
    _conn = conn or get_conn()
    try:
        rows = _conn.execute(
            """SELECT ts.term, ts.avg_lift, ts.acceleration,
                      ts.unique_authors, ts.mention_count
               FROM topic_signals ts
               INNER JOIN (
                   SELECT MAX(id) AS max_id FROM scan_runs
                   WHERE org = ?
                     AND completed_at IS NOT NULL
                     AND (claude_raw IS NULL OR claude_raw NOT LIKE 'FAILED:%')
               ) latest ON ts.scan_id = latest.max_id
               WHERE ts.org = ? AND ts.unique_authors >= ?
               ORDER BY (ts.avg_lift * ts.acceleration * ts.unique_authors) DESC
               LIMIT ?""",
            (org, org, min_unique_authors, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if conn is None:
            _conn.close()


def get_prev_scan_topics(org: str, limit: int = 1) -> dict[str, int]:
    """Get term -> mention_count from most recent scan(s)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT ts.term, ts.mention_count
           FROM topic_signals ts
           INNER JOIN (
               SELECT id FROM scan_runs WHERE org = ? ORDER BY id DESC LIMIT ?
           ) recent ON ts.scan_id = recent.id
           WHERE ts.org = ?""",
        (org, limit, org),
    ).fetchall()
    conn.close()
    result: dict[str, int] = {}
    for row in rows:
        term = row["term"]
        result[term] = result.get(term, 0) + row["mention_count"]
    return result


def get_scan_summary_all_orgs() -> list[dict]:
    """Return [{org, last_scan_at, scan_count}] for all orgs with scan history."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT org,
                  MAX(completed_at) as last_scan_at,
                  COUNT(*) as scan_count
           FROM scan_runs
           GROUP BY org
           ORDER BY last_scan_at DESC NULLS LAST"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
