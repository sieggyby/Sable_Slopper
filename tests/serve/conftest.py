"""Shared fixtures for serve tests."""
from __future__ import annotations

import sqlite3

import pytest


def make_sqlite(schema: str) -> sqlite3.Connection:
    """Create an in-memory SQLite connection safe for cross-thread use."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(schema)
    return conn


PULSE_SCHEMA = """
CREATE TABLE posts (
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
CREATE TABLE snapshots (
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
CREATE TABLE account_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_handle TEXT NOT NULL,
    taken_at TEXT DEFAULT (datetime('now')),
    followers INTEGER DEFAULT 0,
    following INTEGER DEFAULT 0,
    tweet_count INTEGER DEFAULT 0
);
"""

META_SCHEMA = """
CREATE TABLE scan_runs (
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
CREATE TABLE topic_signals (
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
CREATE TABLE format_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    format_bucket TEXT NOT NULL,
    period_days INTEGER NOT NULL,
    avg_total_lift REAL,
    sample_count INTEGER,
    unique_authors INTEGER,
    computed_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE author_profiles (
    author_handle TEXT NOT NULL,
    org TEXT NOT NULL,
    tweet_count INTEGER DEFAULT 0,
    last_seen TEXT,
    last_tweet_id TEXT,
    PRIMARY KEY (author_handle, org)
);
"""
