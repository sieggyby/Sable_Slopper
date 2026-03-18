"""Tests for pulse scoring functions."""
import pytest

from sable.pulse.scorer import (
    engagement_rate,
    virality_score,
    conversation_score,
    score_post,
    percentile_rank,
    rank_posts,
)


def test_engagement_rate_basic():
    er = engagement_rate(likes=100, retweets=20, replies=10, quotes=5, followers=1000)
    assert er == pytest.approx(13.5, rel=0.01)


def test_engagement_rate_zero_followers():
    er = engagement_rate(100, 20, 10, 5, followers=0)
    assert er == 0.0


def test_virality_score():
    vs = virality_score(retweets=50, quotes=10, views=10000)
    assert vs == pytest.approx(6.0, rel=0.01)


def test_virality_zero_views():
    vs = virality_score(10, 5, views=0)
    assert vs == 0.0


def test_conversation_score():
    cs = conversation_score(replies=30, quotes=10, views=5000)
    assert cs == pytest.approx(8.0, rel=0.01)


def test_score_post():
    snap = {"likes": 200, "retweets": 40, "replies": 20, "views": 10000, "quotes": 10, "bookmarks": 5}
    scores = score_post(snap, followers=5000)
    assert "engagement_rate" in scores
    assert "virality_score" in scores
    assert "conversation_score" in scores
    assert scores["likes"] == 200


def test_percentile_rank():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile_rank(3.0, values) == pytest.approx(40.0)
    assert percentile_rank(5.0, values) == pytest.approx(80.0)
    assert percentile_rank(1.0, values) == pytest.approx(0.0)


def test_rank_posts():
    posts = [
        {"engagement_rate": 1.0, "text": "low"},
        {"engagement_rate": 5.0, "text": "high"},
        {"engagement_rate": 2.5, "text": "mid"},
    ]
    ranked = rank_posts(posts)
    assert ranked[0]["text"] == "high"
    assert ranked[0]["rank"] == 1
    assert ranked[-1]["text"] == "low"
