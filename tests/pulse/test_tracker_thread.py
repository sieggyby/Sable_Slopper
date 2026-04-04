"""Tests for thread detection in pulse tracker ingestion."""
from __future__ import annotations

from unittest.mock import patch

from sable.pulse import db as pulse_db


def _make_tweet(tweet_id: str, handle: str, in_reply_to: str = "") -> dict:
    """Build a minimal SocialData tweet dict."""
    t = {
        "id_str": tweet_id,
        "full_text": f"Tweet {tweet_id}",
        "created_at": "2026-04-01T12:00:00Z",
        "user": {"screen_name": handle, "followers_count": 100, "friends_count": 50, "statuses_count": 500},
        "favorite_count": 10,
        "retweet_count": 2,
        "reply_count": 1,
        "views_count": 100,
        "bookmark_count": 1,
        "quote_count": 0,
    }
    if in_reply_to:
        t["in_reply_to_screen_name"] = in_reply_to
    return t


def test_thread_detection_self_reply(tmp_path, monkeypatch):
    """Reply to self → is_thread=1 stored in pulse.db."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)
    (tmp_path / "pulse_cache").mkdir(exist_ok=True)

    from sable.pulse.tracker import snapshot_account

    tweets = [_make_tweet("t1", "alice", in_reply_to="alice")]
    with patch("sable.pulse.tracker.fetch_user_tweets", return_value=tweets):
        snapshot_account("@alice", mock=False)

    conn = pulse_db.get_conn()
    row = conn.execute("SELECT is_thread, thread_length FROM posts WHERE id = 't1'").fetchone()
    conn.close()
    assert row is not None
    assert row["is_thread"] == 1
    assert row["thread_length"] == 2  # floor so classify_format reaches "thread" bucket


def test_thread_detection_reply_to_other(tmp_path, monkeypatch):
    """Reply to different user → is_thread=0."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)
    (tmp_path / "pulse_cache").mkdir(exist_ok=True)

    from sable.pulse.tracker import snapshot_account

    tweets = [_make_tweet("t2", "alice", in_reply_to="bob")]
    with patch("sable.pulse.tracker.fetch_user_tweets", return_value=tweets):
        snapshot_account("@alice", mock=False)

    conn = pulse_db.get_conn()
    row = conn.execute("SELECT is_thread FROM posts WHERE id = 't2'").fetchone()
    conn.close()
    assert row["is_thread"] == 0


def test_thread_detection_no_reply(tmp_path, monkeypatch):
    """No in_reply_to field → is_thread=0."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)
    (tmp_path / "pulse_cache").mkdir(exist_ok=True)

    from sable.pulse.tracker import snapshot_account

    tweets = [_make_tweet("t3", "alice")]
    with patch("sable.pulse.tracker.fetch_user_tweets", return_value=tweets):
        snapshot_account("@alice", mock=False)

    conn = pulse_db.get_conn()
    row = conn.execute("SELECT is_thread FROM posts WHERE id = 't3'").fetchone()
    conn.close()
    assert row["is_thread"] == 0


def test_thread_detection_case_insensitive(tmp_path, monkeypatch):
    """Handle comparison is case-insensitive."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)
    (tmp_path / "pulse_cache").mkdir(exist_ok=True)

    from sable.pulse.tracker import snapshot_account

    tweets = [_make_tweet("t4", "Alice", in_reply_to="ALICE")]
    with patch("sable.pulse.tracker.fetch_user_tweets", return_value=tweets):
        snapshot_account("@Alice", mock=False)

    conn = pulse_db.get_conn()
    row = conn.execute("SELECT is_thread FROM posts WHERE id = 't4'").fetchone()
    conn.close()
    assert row["is_thread"] == 1
