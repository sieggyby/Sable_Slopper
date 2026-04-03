"""Tests for sable/write/scorer.py."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_cache_row(generated_at: str) -> dict:
    return {
        "org": "testorg",
        "format_bucket": "standalone_text",
        "patterns_json": json.dumps([
            {"name": "Bold Claim", "description": "Opens with a strong assertion", "example": "Most devs are wrong about X"},
        ]),
        "generated_at": generated_at,
    }


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class _FakeAccount:
    handle: str = "@testuser"
    org: str = "testorg"


# ---------------------------------------------------------------------------
# _is_cache_stale tests
# ---------------------------------------------------------------------------

def test_cache_fresh_returns_false(monkeypatch):
    from sable.write import scorer
    monkeypatch.setattr(scorer, "get_latest_successful_scan_at", lambda org: None)

    recent = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
    row = _make_cache_row(recent)
    assert scorer._is_cache_stale(row, "testorg") is False


def test_cache_stale_by_age_returns_true(monkeypatch):
    from sable.write import scorer
    monkeypatch.setattr(scorer, "get_latest_successful_scan_at", lambda org: None)

    old = _iso(datetime.now(timezone.utc) - timedelta(hours=25))
    row = _make_cache_row(old)
    assert scorer._is_cache_stale(row, "testorg") is True


def test_cache_stale_by_newer_scan_returns_true(monkeypatch):
    from sable.write import scorer

    generated = datetime.now(timezone.utc) - timedelta(hours=2)
    newer_scan = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
    monkeypatch.setattr(scorer, "get_latest_successful_scan_at", lambda org: newer_scan)

    row = _make_cache_row(_iso(generated))
    assert scorer._is_cache_stale(row, "testorg") is True


# ---------------------------------------------------------------------------
# get_hook_patterns tests
# ---------------------------------------------------------------------------

def test_get_hook_patterns_uses_cache_when_fresh(monkeypatch):
    from sable.write import scorer

    recent = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
    cache_row = _make_cache_row(recent)

    monkeypatch.setattr(scorer, "get_hook_patterns_cache", lambda org, fmt: cache_row)
    monkeypatch.setattr(scorer, "get_latest_successful_scan_at", lambda org: None)
    call_count = {"n": 0}

    def fake_claude(prompt, **kwargs):
        call_count["n"] += 1
        return '{"patterns": []}'

    monkeypatch.setattr(scorer, "call_claude_json", fake_claude)

    result = scorer.get_hook_patterns("testorg", "standalone_text")
    assert call_count["n"] == 0
    assert len(result) == 1
    assert result[0].name == "Bold Claim"


def test_get_hook_patterns_calls_claude_when_stale(monkeypatch):
    from sable.write import scorer

    old = _iso(datetime.now(timezone.utc) - timedelta(hours=25))
    cache_row = _make_cache_row(old)

    monkeypatch.setattr(scorer, "get_hook_patterns_cache", lambda org, fmt: cache_row)
    monkeypatch.setattr(scorer, "get_latest_successful_scan_at", lambda org: None)

    tweets = [
        {"text": f"Tweet {i}", "total_lift": 3.0}
        for i in range(10)
    ]
    monkeypatch.setattr(scorer, "get_high_lift_tweets", lambda *a, **kw: tweets)

    upserted = {"called": False}

    def fake_upsert(org, fmt, patterns_json):
        upserted["called"] = True

    monkeypatch.setattr(scorer, "upsert_hook_patterns", fake_upsert)

    new_patterns = [{"name": "Fresh", "description": "desc", "example": "ex"}]

    def fake_claude(prompt, **kwargs):
        return json.dumps({"patterns": new_patterns})

    monkeypatch.setattr(scorer, "call_claude_json", fake_claude)

    result = scorer.get_hook_patterns("testorg", "standalone_text")
    assert len(result) == 1
    assert result[0].name == "Fresh"
    assert upserted["called"] is True


def test_get_hook_patterns_raises_when_insufficient_tweets(monkeypatch):
    from sable.write import scorer
    from sable.platform.errors import SableError

    monkeypatch.setattr(scorer, "get_hook_patterns_cache", lambda org, fmt: None)
    monkeypatch.setattr(scorer, "get_high_lift_tweets", lambda *a, **kw: [{"text": "t", "total_lift": 3.0}] * 3)

    with pytest.raises(SableError) as exc_info:
        scorer.get_hook_patterns("testorg", "standalone_text")

    assert exc_info.value.code == "NO_SCAN_DATA"


def test_get_hook_patterns_returns_parsed_dataclasses(monkeypatch):
    from sable.write import scorer
    from sable.write.scorer import HookPattern

    monkeypatch.setattr(scorer, "get_hook_patterns_cache", lambda org, fmt: None)

    tweets = [{"text": f"t{i}", "total_lift": 3.0} for i in range(10)]
    monkeypatch.setattr(scorer, "get_high_lift_tweets", lambda *a, **kw: tweets)
    monkeypatch.setattr(scorer, "upsert_hook_patterns", lambda *a, **kw: None)

    patterns_data = [
        {"name": "Contrarian Take", "description": "Challenges consensus", "example": "Everyone is wrong about X"},
        {"name": "Number Hook", "description": "Leads with a number", "example": "3 things nobody tells you"},
    ]

    monkeypatch.setattr(scorer, "call_claude_json", lambda *a, **kw: json.dumps({"patterns": patterns_data}))

    result = scorer.get_hook_patterns("testorg", "standalone_text")
    assert all(isinstance(p, HookPattern) for p in result)
    assert result[0].name == "Contrarian Take"
    assert result[1].name == "Number Hook"


# ---------------------------------------------------------------------------
# score_draft tests
# ---------------------------------------------------------------------------

def _patch_score_draft_deps(monkeypatch, score: float = 8.0, include_rewrite: bool = False):
    from sable.write import scorer

    monkeypatch.setattr(scorer, "require_account", lambda handle: _FakeAccount())

    patterns = [scorer.HookPattern(name="Bold Claim", description="desc", example="ex")]
    monkeypatch.setattr(scorer, "get_hook_patterns", lambda org, fmt: patterns)

    response: dict = {
        "grade": "A",
        "score": score,
        "matched_pattern": "Bold Claim",
        "voice_fit": 8,
        "flags": ["too long"],
    }
    if include_rewrite:
        response["suggested_rewrite"] = "Rewritten version"

    monkeypatch.setattr(scorer, "call_claude_json", lambda *a, **kw: json.dumps(response))


def test_score_draft_returns_hook_score(monkeypatch, tmp_path):
    from sable.write import scorer
    from sable.write.scorer import HookScore

    monkeypatch.setattr(scorer, "profile_dir", lambda handle: tmp_path)
    _patch_score_draft_deps(monkeypatch, score=8.0)

    result = scorer.score_draft("@testuser", "Some draft text", "standalone_text", "testorg")
    assert isinstance(result, HookScore)
    assert result.grade == "A"
    assert result.score == 8.0
    assert result.flags == ["too long"]


def test_score_draft_no_suggested_rewrite_when_score_high(monkeypatch, tmp_path):
    from sable.write import scorer

    monkeypatch.setattr(scorer, "profile_dir", lambda handle: tmp_path)
    _patch_score_draft_deps(monkeypatch, score=9.0, include_rewrite=False)

    result = scorer.score_draft("@testuser", "Strong draft", "standalone_text", "testorg")
    assert result.suggested_rewrite is None


def test_score_draft_includes_suggested_rewrite_when_score_low(monkeypatch, tmp_path):
    from sable.write import scorer

    monkeypatch.setattr(scorer, "profile_dir", lambda handle: tmp_path)
    _patch_score_draft_deps(monkeypatch, score=5.0, include_rewrite=True)

    result = scorer.score_draft("@testuser", "Weak draft", "standalone_text", "testorg")
    assert result.suggested_rewrite == "Rewritten version"


def test_score_draft_uses_org_from_account_when_not_provided(monkeypatch, tmp_path):
    from sable.write import scorer

    monkeypatch.setattr(scorer, "profile_dir", lambda handle: tmp_path)

    captured = {"org": None}

    def fake_get_patterns(org, fmt):
        captured["org"] = org
        return [scorer.HookPattern(name="P", description="d", example="e")]

    monkeypatch.setattr(scorer, "require_account", lambda handle: _FakeAccount(org="account_org"))
    monkeypatch.setattr(scorer, "get_hook_patterns", fake_get_patterns)
    monkeypatch.setattr(scorer, "call_claude_json", lambda *a, **kw: json.dumps({
        "grade": "B", "score": 7.0, "matched_pattern": None, "voice_fit": 7, "flags": [],
    }))

    scorer.score_draft("@testuser", "draft", "standalone_text", org=None)
    assert captured["org"] == "account_org"


def test_score_draft_propagates_sable_error(monkeypatch, tmp_path):
    from sable.write import scorer
    from sable.platform.errors import SableError

    monkeypatch.setattr(scorer, "profile_dir", lambda handle: tmp_path)
    monkeypatch.setattr(scorer, "require_account", lambda handle: _FakeAccount())
    monkeypatch.setattr(
        scorer, "get_hook_patterns",
        lambda org, fmt: (_ for _ in ()).throw(SableError("NO_SCAN_DATA", "not enough tweets")),
    )

    with pytest.raises(SableError) as exc_info:
        scorer.score_draft("@testuser", "draft", "standalone_text", "testorg")

    assert exc_info.value.code == "NO_SCAN_DATA"


# ---------------------------------------------------------------------------
# org_id threading tests (AUDIT-5)
# ---------------------------------------------------------------------------

def test_get_hook_patterns_passes_org_id_to_claude(monkeypatch):
    """get_hook_patterns passes org_id to call_claude_json."""
    from sable.write import scorer

    monkeypatch.setattr(scorer, "get_hook_patterns_cache", lambda org, fmt: None)
    tweets = [{"text": f"t{i}", "total_lift": 3.0} for i in range(10)]
    monkeypatch.setattr(scorer, "get_high_lift_tweets", lambda *a, **kw: tweets)
    monkeypatch.setattr(scorer, "upsert_hook_patterns", lambda *a, **kw: None)

    captured_kwargs = {}

    def fake_claude(*a, **kw):
        captured_kwargs.update(kw)
        return json.dumps({"patterns": [{"name": "P", "description": "d", "example": "e"}]})

    monkeypatch.setattr(scorer, "call_claude_json", fake_claude)
    scorer.get_hook_patterns("myorg", "standalone_text")
    assert captured_kwargs.get("org_id") == "myorg"


def test_score_draft_passes_org_id_to_claude(monkeypatch, tmp_path):
    """score_draft passes resolved_org to call_claude_json."""
    from sable.write import scorer

    monkeypatch.setattr(scorer, "profile_dir", lambda handle: tmp_path)
    monkeypatch.setattr(scorer, "require_account", lambda handle: _FakeAccount(org="testorg"))

    patterns = [scorer.HookPattern(name="P", description="d", example="e")]
    monkeypatch.setattr(scorer, "get_hook_patterns", lambda org, fmt: patterns)

    captured_kwargs = {}

    def fake_claude(*a, **kw):
        captured_kwargs.update(kw)
        return json.dumps({"grade": "B", "score": 7.0, "matched_pattern": None, "voice_fit": 7, "flags": []})

    monkeypatch.setattr(scorer, "call_claude_json", fake_claude)
    scorer.score_draft("@testuser", "draft", "standalone_text", org="testorg")
    assert captured_kwargs.get("org_id") == "testorg"
