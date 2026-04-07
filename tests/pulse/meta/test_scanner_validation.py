"""Tests for _normalise_tweet field validation (AUDIT-2)."""
from __future__ import annotations


def _valid_raw_tweet(**overrides) -> dict:
    """Minimal valid SocialData tweet payload."""
    base = {
        "id_str": "1234567890",
        "full_text": "gm crypto twitter",
        "created_at": "Thu Mar 17 12:00:00 +0000 2026",
        "user": {"screen_name": "testuser", "followers_count": 500},
        "favorite_count": 10,
        "reply_count": 2,
        "retweet_count": 3,
        "quote_count": 0,
        "bookmark_count": 1,
        "views_count": 200,
    }
    base.update(overrides)
    return base


def test_normalise_tweet_valid_returns_dict():
    from sable.pulse.meta.scanner import _normalise_tweet

    result = _normalise_tweet(_valid_raw_tweet(), "@testuser")
    assert result is not None
    assert result["tweet_id"] == "1234567890"
    assert result["posted_at"] is not None


def test_normalise_tweet_missing_id_returns_none():
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet()
    del raw["id_str"]
    # Also ensure "id" is absent
    raw.pop("id", None)
    result = _normalise_tweet(raw, "@testuser")
    assert result is None


def test_normalise_tweet_empty_id_returns_none():
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet(id_str="", id="")
    result = _normalise_tweet(raw, "@testuser")
    assert result is None


def test_normalise_tweet_unparseable_date_returns_none():
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet(created_at="not-a-date")
    result = _normalise_tweet(raw, "@testuser")
    assert result is None


def test_normalise_tweet_empty_date_returns_none():
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet(created_at="")
    result = _normalise_tweet(raw, "@testuser")
    assert result is None


def test_normalise_tweet_missing_all_engagement_fields_returns_none():
    """If none of the core engagement counters are present, reject the tweet."""
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet()
    del raw["favorite_count"]
    del raw["reply_count"]
    del raw["retweet_count"]
    # quote_count, bookmark_count, views_count are not core — their absence alone is fine
    result = _normalise_tweet(raw, "@testuser")
    assert result is None


def test_normalise_tweet_partial_engagement_fields_rejected():
    """Missing any core engagement counter rejects the tweet (no silent zero-fill)."""
    from sable.pulse.meta.scanner import _normalise_tweet

    # Missing reply_count + retweet_count
    raw = _valid_raw_tweet()
    del raw["reply_count"]
    del raw["retweet_count"]
    assert _normalise_tweet(raw, "@testuser") is None


def test_normalise_tweet_missing_only_favorite_count_rejected():
    """Missing only favorite_count rejects the tweet."""
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet()
    del raw["favorite_count"]
    assert _normalise_tweet(raw, "@testuser") is None


def test_normalise_tweet_missing_only_reply_count_rejected():
    """Missing only reply_count rejects the tweet."""
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet()
    del raw["reply_count"]
    assert _normalise_tweet(raw, "@testuser") is None


def test_normalise_tweet_missing_only_retweet_count_rejected():
    """Missing only retweet_count rejects the tweet."""
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet()
    del raw["retweet_count"]
    assert _normalise_tweet(raw, "@testuser") is None


def test_mixed_batch_partial_core_counters_excluded():
    """Tweets with partial core counters do not enter the normal analytics path."""
    from sable.pulse.meta.scanner import _normalise_tweet

    good = _valid_raw_tweet(id_str="111")
    partial1 = _valid_raw_tweet(id_str="222")
    del partial1["favorite_count"]
    partial2 = _valid_raw_tweet(id_str="333")
    del partial2["reply_count"]
    good2 = _valid_raw_tweet(id_str="444")

    results = [_normalise_tweet(t, "@user") for t in [good, partial1, partial2, good2]]
    valid = [r for r in results if r is not None]
    assert len(valid) == 2
    assert {r["tweet_id"] for r in valid} == {"111", "444"}


def test_normalise_tweet_zero_engagement_accepted():
    """A tweet with explicitly zero engagement is valid — not malformed."""
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet(favorite_count=0, reply_count=0, retweet_count=0)
    result = _normalise_tweet(raw, "@testuser")
    assert result is not None
    assert result["likes"] == 0


def test_normalise_tweet_non_numeric_core_engagement_rejected():
    """Non-numeric core engagement value rejects the tweet (provider drift guard)."""
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet(favorite_count="not_a_number")
    result = _normalise_tweet(raw, "@testuser")
    assert result is None


def test_normalise_tweet_non_numeric_non_core_engagement_coerced():
    """Non-numeric non-core engagement (e.g. quote_count) is coerced to 0 via _safe_int."""
    from sable.pulse.meta.scanner import _normalise_tweet

    raw = _valid_raw_tweet(quote_count="garbage")
    result = _normalise_tweet(raw, "@testuser")
    assert result is not None
    assert result["quotes"] == 0
    assert isinstance(result["quotes"], int)


def test_mixed_batch_skips_malformed():
    """A batch with one malformed tweet still normalises the valid ones."""
    from sable.pulse.meta.scanner import _normalise_tweet

    good1 = _valid_raw_tweet(id_str="111")
    bad = _valid_raw_tweet(id_str="")  # empty id
    bad.pop("id", None)
    good2 = _valid_raw_tweet(id_str="222")

    results = [_normalise_tweet(t, "@user") for t in [good1, bad, good2]]
    valid = [r for r in results if r is not None]
    assert len(valid) == 2
    assert {r["tweet_id"] for r in valid} == {"111", "222"}


def test_scanner_batch_warns_on_skipped_malformed_tweets(capsys, monkeypatch):
    """Scanner.run emits a warning when malformed tweets are skipped in a batch."""
    import sqlite3
    from unittest.mock import MagicMock, patch, AsyncMock
    from sable.pulse.meta.scanner import Scanner
    from sable.pulse.meta.db import _SCHEMA

    good = _valid_raw_tweet(id_str="111")
    bad = _valid_raw_tweet(id_str="222")
    del bad["favorite_count"]
    del bad["reply_count"]
    del bad["retweet_count"]

    # Stub DB
    mock_db = MagicMock()
    mock_db.get_completed_authors.return_value = set()
    mock_db.get_author_profile.return_value = None
    mock_db.get_author_tweets.return_value = []
    mock_db.upsert_tweet.return_value = True
    mock_db.upsert_author_profile.return_value = None
    mock_db.checkpoint_author.return_value = None

    # Provide an in-memory meta.db so bulk_upsert_tweets works.
    # Use shared cache so each _meta_get_conn() call returns a fresh
    # connection to the same in-memory DB (scanner closes per-author).
    _db_uri = "file:test_scanner_validation?mode=memory&cache=shared"
    init_conn = sqlite3.connect(_db_uri, uri=True)
    init_conn.row_factory = sqlite3.Row
    for stmt in _SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            init_conn.execute(stmt)

    def _fresh_conn():
        c = sqlite3.connect(_db_uri, uri=True)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr("sable.pulse.meta.scanner._meta_get_conn", _fresh_conn)

    # Stub classify + normalize
    mock_lift = MagicMock()
    for attr in ("author_median_likes", "author_median_replies",
                 "author_median_reposts", "author_median_quotes",
                 "author_median_total", "author_median_same_format",
                 "likes_lift", "replies_lift", "reposts_lift",
                 "quotes_lift", "total_lift", "format_lift",
                 "format_lift_reliable"):
        setattr(mock_lift, attr, 0.0)
    mock_lift.author_quality = MagicMock(grade="C", weight=0.5)

    scanner = Scanner(
        org="testorg",
        watchlist=[{"handle": "@user"}],
        db=mock_db,
        max_cost=10.0,
    )

    async def fake_fetch(handle, **kw):
        return [good, bad], 1

    with patch("sable.pulse.meta.scanner._fetch_author_tweets_async", side_effect=fake_fetch), \
         patch("sable.pulse.meta.fingerprint.classify_tweet", return_value=("text", {})), \
         patch("sable.pulse.meta.normalize.compute_author_lift", return_value=mock_lift):
        result = scanner.run(scan_id=1)

    assert result["tweets_collected"] == 1
    captured = capsys.readouterr()
    assert "Skipped 1 malformed" in captured.err
