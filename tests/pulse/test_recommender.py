"""Tests for pulse/recommender.py — generate_recommendations()."""
from __future__ import annotations

import json

import pytest

from sable.roster.models import Account


def _make_account(handle="@testaccount") -> Account:
    return Account(handle=handle)


def _make_snapshot(post_id: str, likes=10, retweets=2, replies=1, quotes=0, views=500, bookmarks=0) -> dict:
    return {
        "post_id": post_id,
        "likes": likes,
        "retweets": retweets,
        "replies": replies,
        "quotes": quotes,
        "views": views,
        "bookmarks": bookmarks,
    }


def _make_post(post_id: str, text: str = "test post", content_type: str = "tweet") -> dict:
    return {"id": post_id, "text": text, "sable_content_type": content_type}


# ─────────────────────────────────────────────────────────────────────
# generate_recommendations — with mocked DB and Claude
# ─────────────────────────────────────────────────────────────────────

def test_generate_recommendations_returns_empty_summary_when_no_data(monkeypatch):
    """When no posts have snapshots, returns the no-data summary dict."""
    monkeypatch.setattr("sable.pulse.recommender.get_posts_for_account", lambda handle, limit: [])
    monkeypatch.setattr("sable.pulse.recommender.save_recommendation", lambda h, c: None)

    from sable.pulse.recommender import generate_recommendations
    result = generate_recommendations(_make_account(), followers=1000)

    assert "summary" in result
    assert "Track posts first" in result["summary"]
    assert result["recommendations"] == []


def test_generate_recommendations_calls_claude_once(monkeypatch):
    """With post data, Claude is called exactly once."""
    posts = [_make_post("p1", "DeFi post"), _make_post("p2", "NFT post")]
    snaps = {"p1": _make_snapshot("p1"), "p2": _make_snapshot("p2")}
    claude_calls = []

    fake_result = {"summary": "ok", "recommendations": [], "content_ideas": [], "avoid": []}

    monkeypatch.setattr("sable.pulse.recommender.get_posts_for_account", lambda h, limit: posts)
    monkeypatch.setattr("sable.pulse.recommender.get_latest_snapshot", lambda pid: snaps.get(pid))
    monkeypatch.setattr("sable.pulse.recommender.save_recommendation", lambda h, c: None)
    monkeypatch.setattr("sable.pulse.recommender.call_claude_json", lambda prompt, **kw: (claude_calls.append(1) or json.dumps(fake_result)))

    from sable.pulse.recommender import generate_recommendations
    generate_recommendations(_make_account(), followers=1000)
    assert len(claude_calls) == 1


def test_generate_recommendations_returns_dict_with_keys(monkeypatch):
    """Mock response is parsed and returned as a dict with expected keys."""
    posts = [_make_post("p1")]
    snaps = {"p1": _make_snapshot("p1")}

    fake_result = {
        "summary": "Good performance.",
        "recommendations": [{"priority": "high", "type": "format", "action": "Post more clips", "rationale": "clips outperform"}],
        "content_ideas": ["Post about staking"],
        "avoid": ["Long threads"],
    }

    monkeypatch.setattr("sable.pulse.recommender.get_posts_for_account", lambda h, limit: posts)
    monkeypatch.setattr("sable.pulse.recommender.get_latest_snapshot", lambda pid: snaps.get(pid))
    monkeypatch.setattr("sable.pulse.recommender.save_recommendation", lambda h, c: None)
    monkeypatch.setattr("sable.pulse.recommender.call_claude_json", lambda prompt, **kw: json.dumps(fake_result))

    from sable.pulse.recommender import generate_recommendations
    result = generate_recommendations(_make_account(), followers=1000)

    for key in ("summary", "recommendations", "content_ideas", "avoid"):
        assert key in result
    assert result["summary"] == "Good performance."


def test_generate_recommendations_top_post_in_prompt(monkeypatch):
    """The top-performing post (highest engagement_rate) appears first in the Claude prompt."""
    posts = [
        _make_post("low", "Low engagement post"),
        _make_post("high", "High engagement post"),
    ]
    snaps = {
        "low": _make_snapshot("low", likes=1, retweets=0, replies=0, quotes=0, views=1000),
        "high": _make_snapshot("high", likes=100, retweets=20, replies=10, quotes=5, views=1000),
    }
    prompts_seen = []
    fake_result = {"summary": "ok", "recommendations": [], "content_ideas": [], "avoid": []}

    monkeypatch.setattr("sable.pulse.recommender.get_posts_for_account", lambda h, limit: posts)
    monkeypatch.setattr("sable.pulse.recommender.get_latest_snapshot", lambda pid: snaps.get(pid))
    monkeypatch.setattr("sable.pulse.recommender.save_recommendation", lambda h, c: None)
    monkeypatch.setattr(
        "sable.pulse.recommender.call_claude_json",
        lambda prompt, **kw: (prompts_seen.append(prompt) or json.dumps(fake_result))
    )

    from sable.pulse.recommender import generate_recommendations
    generate_recommendations(_make_account(), followers=1000)

    assert prompts_seen, "Claude was not called"
    prompt = prompts_seen[0]
    # High post appears before low post in "Top Performing" section
    assert prompt.index("High engagement post") < prompt.index("Low engagement post")
