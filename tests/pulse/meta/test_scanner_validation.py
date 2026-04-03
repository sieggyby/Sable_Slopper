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
