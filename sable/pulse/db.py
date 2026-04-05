"""SQLite schema and migration for pulse performance tracking."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from sable.shared.paths import pulse_db_path

SCHEMA_VERSION = 2

# Keyed by target version: callable(conn) that applies ALTERs for version N-1 → N.
# Version 1→2: is_thread and thread_length columns were added to CREATE TABLE
#               without a version bump. No ALTER needed (columns exist via CREATE),
#               but version now tracked.
_MIGRATIONS: dict[int, list[str]] = {
    # 2: []  — columns already in CREATE TABLE, version catch-up only
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    account_handle TEXT NOT NULL,
    platform TEXT DEFAULT 'twitter',
    url TEXT,
    text TEXT,
    posted_at TEXT,
    sable_content_type TEXT,  -- clip | meme | faceswap | text | unknown
    sable_content_path TEXT,
    is_thread INTEGER DEFAULT 0,
    thread_length INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL REFERENCES posts(id),
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

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_handle TEXT NOT NULL,
    generated_at TEXT DEFAULT (datetime('now')),
    content TEXT,
    applied INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_posts_account ON posts(account_handle);
CREATE INDEX IF NOT EXISTS idx_snapshots_post ON snapshots(post_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_taken ON snapshots(taken_at);
"""


def get_conn() -> sqlite3.Connection:
    path = pulse_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def migrate() -> None:
    """Initialize or migrate the pulse database."""
    import logging
    _logger = logging.getLogger(__name__)

    conn = get_conn()
    with conn:
        conn.executescript(_SCHEMA)
        version_row = conn.execute("SELECT version FROM schema_version").fetchone()
        if version_row is None:
            conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
            _logger.info("pulse.db initialized at schema version %d", SCHEMA_VERSION)
        else:
            current = version_row[0] if not hasattr(version_row, "keys") else version_row["version"]
            if current < SCHEMA_VERSION:
                for target_v in range(current + 1, SCHEMA_VERSION + 1):
                    stmts = _MIGRATIONS.get(target_v, [])
                    for stmt in stmts:
                        conn.execute(stmt)
                    _logger.info("pulse.db migrated %d → %d", target_v - 1, target_v)
                conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
                _logger.info(
                    "pulse.db schema version %d → %d",
                    current, SCHEMA_VERSION,
                )
            elif current > SCHEMA_VERSION:
                _logger.warning(
                    "pulse.db version %d is ahead of code version %d — skipping migration",
                    current, SCHEMA_VERSION,
                )
    conn.close()


def insert_post(
    post_id: str,
    account_handle: str,
    text: str = "",
    url: str = "",
    posted_at: str = "",
    platform: str = "twitter",
    content_type: str = "unknown",
    content_path: str = "",
    is_thread: bool = False,
    thread_length: int = 1,
) -> bool:
    """Insert a post. Returns True if newly inserted, False if already existed (AR5-24)."""
    # Normalize handle to always include @ prefix (matches get_posts_for_account convention)
    account_handle = account_handle if account_handle.startswith("@") else f"@{account_handle}"
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM posts WHERE id = ?", (post_id,)
    ).fetchone()
    if existing:
        conn.close()
        return False
    with conn:
        conn.execute(
            """INSERT INTO posts
               (id, account_handle, platform, url, text, posted_at,
                sable_content_type, sable_content_path, is_thread, thread_length)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (post_id, account_handle, platform, url, text, posted_at,
             content_type, content_path, int(is_thread), thread_length),
        )
    conn.close()
    return True


def insert_snapshot(
    post_id: str,
    likes: int = 0,
    retweets: int = 0,
    replies: int = 0,
    views: int = 0,
    bookmarks: int = 0,
    quotes: int = 0,
) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """INSERT INTO snapshots (post_id, likes, retweets, replies, views, bookmarks, quotes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (post_id, likes, retweets, replies, views, bookmarks, quotes),
        )
    conn.close()


def get_latest_snapshot(post_id: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM snapshots WHERE post_id = ? ORDER BY taken_at DESC LIMIT 1",
        (post_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_posts_for_account(account_handle: str, limit: int = 100) -> list[dict]:
    handle = account_handle if account_handle.startswith("@") else f"@{account_handle}"
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM posts WHERE account_handle = ? ORDER BY posted_at DESC LIMIT ?",
        (handle, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_account_stats(handle: str, followers: int, following: int, tweet_count: int) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO account_stats (account_handle, followers, following, tweet_count) VALUES (?, ?, ?, ?)",
            (handle, followers, following, tweet_count),
        )
    conn.close()


def save_recommendation(handle: str, content: str) -> int:
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO recommendations (account_handle, content) VALUES (?, ?)",
        (handle, content),
    )
    assert cursor.lastrowid is not None
    rec_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return rec_id
