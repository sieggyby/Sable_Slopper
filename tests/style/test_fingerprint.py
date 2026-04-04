"""Tests for sable.style.fingerprint — format distribution analysis."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from sable.pulse.db import _SCHEMA as PULSE_SCHEMA
from sable.pulse.meta.db import _SCHEMA as META_SCHEMA
from sable.style.fingerprint import (
    _coarse_bucket,
    fingerprint_managed,
    fingerprint_watchlist,
    MIN_POSTS,
)

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int = 0) -> str:
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _make_pulse_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(PULSE_SCHEMA)
    return conn


def _make_meta_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(META_SCHEMA)
    return conn


def _insert_post(conn, handle, content_type, days_ago=0):
    pid = str(uuid.uuid4())[:12]
    conn.execute(
        "INSERT INTO posts (id, account_handle, sable_content_type, posted_at) VALUES (?, ?, ?, ?)",
        (pid, handle, content_type, _ts(days_ago)),
    )
    conn.commit()


def _insert_scanned(conn, org, author, fmt, total_lift=5.0, days_ago=0,
                     has_image=0, has_video=0, has_link=0, is_thread=0, thread_length=1):
    tid = str(uuid.uuid4())[:12]
    conn.execute(
        """INSERT INTO scanned_tweets
           (tweet_id, org, author_handle, posted_at, text, format_bucket, total_lift,
            has_image, has_video, has_link, is_thread, thread_length,
            likes, replies, reposts, quotes, bookmarks)
           VALUES (?, ?, ?, ?, 'test', ?, ?, ?, ?, ?, ?, ?, 10, 5, 3, 1, 0)""",
        (tid, org, author, _ts(days_ago), fmt, total_lift,
         has_image, has_video, has_link, is_thread, thread_length),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# _coarse_bucket
# ---------------------------------------------------------------------------

def test_coarse_bucket_text():
    assert _coarse_bucket("standalone_text") == "text"
    assert _coarse_bucket("thread") == "text"
    assert _coarse_bucket("quote_tweet") == "text"


def test_coarse_bucket_clip():
    assert _coarse_bucket("short_clip") == "clip"
    assert _coarse_bucket("long_video") == "clip"


def test_coarse_bucket_content_types():
    """sable_content_type values from posts table mapped correctly."""
    assert _coarse_bucket("text") == "text"
    assert _coarse_bucket("clip") == "clip"
    assert _coarse_bucket("meme") == "image"
    assert _coarse_bucket("faceswap") == "image"
    assert _coarse_bucket("unknown") == "other"


def test_coarse_bucket_fallthrough():
    """Unknown format falls through as-is."""
    assert _coarse_bucket("weird_format") == "weird_format"


# ---------------------------------------------------------------------------
# fingerprint_managed
# ---------------------------------------------------------------------------

def test_managed_basic():
    """Managed fingerprint computes format distribution."""
    conn = _make_pulse_conn()
    for _ in range(8):
        _insert_post(conn, "@test", "text")
    for _ in range(2):
        _insert_post(conn, "@test", "clip")
    # 10 posts total = exactly MIN_POSTS
    fp = fingerprint_managed("@test", conn)
    assert fp["text"] == pytest.approx(0.8)
    assert fp["clip"] == pytest.approx(0.2)


def test_managed_below_min_posts():
    """Fewer than MIN_POSTS returns empty dict."""
    conn = _make_pulse_conn()
    for _ in range(5):
        _insert_post(conn, "@test", "text")
    assert fingerprint_managed("@test", conn) == {}


def test_managed_with_meta_enrichment():
    """When meta_conn provided, adds media_rate and link_rate."""
    pulse = _make_pulse_conn()
    meta = _make_meta_conn()

    for _ in range(10):
        _insert_post(pulse, "@test", "text")

    for i in range(5):
        _insert_scanned(meta, "org", "@test", "standalone_text",
                        has_image=1 if i < 2 else 0,
                        has_link=1 if i < 3 else 0)

    fp = fingerprint_managed("@test", pulse, meta)
    assert fp["text"] == 1.0
    assert fp["media_rate"] == pytest.approx(2 / 5)
    assert fp["link_rate"] == pytest.approx(3 / 5)


def test_managed_only_pulse():
    """Without meta_conn, only format distribution (no enrichment keys)."""
    conn = _make_pulse_conn()
    for _ in range(10):
        _insert_post(conn, "@test", "text")

    fp = fingerprint_managed("@test", conn, meta_conn=None)
    assert "text" in fp
    assert "media_rate" not in fp


# ---------------------------------------------------------------------------
# fingerprint_watchlist
# ---------------------------------------------------------------------------

def test_watchlist_basic():
    """Watchlist fingerprint from top performers."""
    meta = _make_meta_conn()

    # 10 authors, 6 posts each — top quintile (2 authors) × 6 posts = 12 >= MIN_POSTS
    for i in range(10):
        for j in range(6):
            fmt = "standalone_text" if j < 4 else "short_clip"
            _insert_scanned(meta, "org", f"@a{i}", fmt, total_lift=float(5 + i))

    fp = fingerprint_watchlist("org", meta)
    assert fp  # not empty
    assert "text" in fp
    assert "clip" in fp
    total_share = sum(v for k, v in fp.items() if k not in {"media_rate", "link_rate", "avg_thread_length"})
    assert total_share == pytest.approx(1.0, abs=0.01)


def test_watchlist_below_min():
    """Fewer than MIN_POSTS returns empty."""
    meta = _make_meta_conn()
    for i in range(3):
        _insert_scanned(meta, "org", f"@a{i}", "standalone_text")

    assert fingerprint_watchlist("org", meta) == {}


def test_watchlist_no_quintile():
    """top_quintile=False uses all authors."""
    meta = _make_meta_conn()
    for i in range(5):
        for j in range(3):
            _insert_scanned(meta, "org", f"@a{i}", "standalone_text", total_lift=1.0)
    # 15 total >= MIN_POSTS=10

    fp = fingerprint_watchlist("org", meta, top_quintile=False)
    assert fp  # not empty


def test_identical_distributions_zero_gap():
    """Identical managed and watchlist → all gaps zero."""
    from sable.style.delta import compute_delta

    fp = {"text": 0.7, "clip": 0.3}
    delta = compute_delta(fp, fp)
    assert delta is not None
    for v in delta.values():
        assert v == pytest.approx(0.0)
