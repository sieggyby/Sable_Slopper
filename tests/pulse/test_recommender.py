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


def _make_posts_and_snaps(n: int) -> tuple[list[dict], dict]:
    """Build n posts with matching snapshots."""
    posts = [_make_post(f"p{i}", f"Post {i} about crypto") for i in range(n)]
    snaps = {f"p{i}": _make_snapshot(f"p{i}", likes=10 + i, views=500) for i in range(n)}
    return posts, snaps


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


def test_generate_recommendations_thin_sample_returns_insufficiency(monkeypatch):
    """With fewer than MIN_SAMPLE posts, returns insufficiency without calling Claude."""
    posts = [_make_post("p1", "DeFi post"), _make_post("p2", "NFT post")]
    snaps = {"p1": _make_snapshot("p1"), "p2": _make_snapshot("p2")}
    claude_calls = []

    monkeypatch.setattr("sable.pulse.recommender.get_posts_for_account", lambda h, limit: posts)
    monkeypatch.setattr("sable.pulse.recommender.get_latest_snapshot", lambda pid: snaps.get(pid))
    monkeypatch.setattr("sable.pulse.recommender.save_recommendation", lambda h, c: None)
    monkeypatch.setattr("sable.pulse.recommender.call_claude_json", lambda prompt, **kw: (claude_calls.append(1) or "{}"))

    from sable.pulse.recommender import generate_recommendations
    result = generate_recommendations(_make_account(), followers=1000)

    assert "need at least" in result["summary"]
    assert result["recommendations"] == []
    assert len(claude_calls) == 0


def test_generate_recommendations_calls_claude_once(monkeypatch):
    """With enough post data, Claude is called exactly once."""
    posts, snaps = _make_posts_and_snaps(6)
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
    posts, snaps = _make_posts_and_snaps(6)

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
        _make_post("p3", "Post three"),
        _make_post("p4", "Post four"),
        _make_post("p5", "Post five"),
    ]
    snaps = {
        "low": _make_snapshot("low", likes=1, retweets=0, replies=0, quotes=0, views=1000),
        "high": _make_snapshot("high", likes=100, retweets=20, replies=10, quotes=5, views=1000),
        "p3": _make_snapshot("p3"),
        "p4": _make_snapshot("p4"),
        "p5": _make_snapshot("p5"),
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


def test_generate_recommendations_passes_org_id_to_claude(monkeypatch):
    """Claude call receives org_id from account.org."""
    posts, snaps = _make_posts_and_snaps(6)
    captured_kwargs = {}

    fake_result = {"summary": "ok", "recommendations": [], "content_ideas": [], "avoid": []}

    monkeypatch.setattr("sable.pulse.recommender.get_posts_for_account", lambda h, limit: posts)
    monkeypatch.setattr("sable.pulse.recommender.get_latest_snapshot", lambda pid: snaps.get(pid))
    monkeypatch.setattr("sable.pulse.recommender.save_recommendation", lambda h, c: None)
    monkeypatch.setattr(
        "sable.pulse.recommender.call_claude_json",
        lambda prompt, **kw: (captured_kwargs.update(kw) or json.dumps(fake_result))
    )

    from sable.pulse.recommender import generate_recommendations
    account = _make_account()
    account.org = "testorg"
    generate_recommendations(account, followers=1000)

    assert captured_kwargs.get("org_id") == "testorg"
