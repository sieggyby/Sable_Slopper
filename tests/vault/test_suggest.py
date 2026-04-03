"""Tests for vault/suggest.py — _note_title() and fetch_tweet_text() URL validation."""
from __future__ import annotations

import pytest

from sable.vault.suggest import _note_title, fetch_tweet_text


# ─────────────────────────────────────────────────────────────────────
# _note_title
# ─────────────────────────────────────────────────────────────────────

def test_note_title_clip_returns_caption():
    note = {"type": "clip", "caption": "DeFi explained", "id": "clip-1"}
    title = _note_title(note)
    assert "DeFi explained" in title


def test_note_title_meme_returns_template_and_topic():
    note = {"type": "meme", "template": "drake", "topic": "NFT season"}
    title = _note_title(note)
    assert "drake" in title
    assert "NFT season" in title


def test_note_title_faceswap_returns_id():
    note = {"type": "faceswap", "id": "faceswap-42"}
    title = _note_title(note)
    assert "faceswap-42" in title


def test_note_title_explainer_returns_topic():
    note = {"type": "explainer", "topic": "bitcoin"}
    title = _note_title(note)
    assert "bitcoin" in title


def test_note_title_unknown_type_returns_non_empty_fallback():
    # Unknown type falls through to note.get("id", "?") — should not crash
    note = {"type": "video"}
    title = _note_title(note)
    assert isinstance(title, str)
    assert len(title) > 0


def test_note_title_unknown_type_missing_keys_does_not_crash():
    # Empty note with no keys — all .get() calls default gracefully
    title = _note_title({})
    assert isinstance(title, str)


# ─────────────────────────────────────────────────────────────────────
# fetch_tweet_text — URL validation path (no HTTP call)
# ─────────────────────────────────────────────────────────────────────

def test_fetch_tweet_text_raises_on_non_url(monkeypatch):
    # Patch require_key so we don't need a real config
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-api-key")
    with pytest.raises(ValueError, match="Cannot extract tweet ID"):
        fetch_tweet_text("not-a-url-at-all")


def test_fetch_tweet_text_raises_on_url_without_status(monkeypatch):
    monkeypatch.setattr("sable.config.require_key", lambda k: "fake-api-key")
    with pytest.raises(ValueError, match="Cannot extract tweet ID"):
        fetch_tweet_text("https://twitter.com/user/no-status-here")


# ─────────────────────────────────────────────────────────────────────
# _draft_reply_texts — org_id threading and warning behavior (AUDIT-5/7)
# ─────────────────────────────────────────────────────────────────────

from unittest.mock import patch, MagicMock
from sable.vault.suggest import _draft_reply_texts, ReplySuggestion
from sable.vault.config import VaultConfig


def _make_suggestion(content_id="c1"):
    return ReplySuggestion(
        content_id=content_id,
        content_title="Test Content",
        content_type="clip",
        content_path="/vault/clip.md",
        account="@test",
        relevance_score=80,
        relevance_reason="relevant",
    )


def test_draft_reply_texts_passes_org_id_to_claude():
    """_draft_reply_texts passes org_id to call_claude_json."""
    suggestions = [_make_suggestion()]
    captured_kwargs = {}

    def fake_claude(*a, **kw):
        captured_kwargs.update(kw)
        return '[{"content_id": "c1", "reply_draft": "nice"}]'

    config = VaultConfig()
    with patch("sable.shared.api.call_claude_json", fake_claude):
        _draft_reply_texts(suggestions, "test tweet", "myorg", "@test", config)

    assert captured_kwargs.get("org_id") == "myorg"


def test_draft_reply_texts_empty_org_sends_none():
    """Empty org sends org_id=None, not empty string."""
    suggestions = [_make_suggestion()]
    captured_kwargs = {}

    def fake_claude(*a, **kw):
        captured_kwargs.update(kw)
        return '[{"content_id": "c1", "reply_draft": "nice"}]'

    config = VaultConfig()
    with patch("sable.shared.api.call_claude_json", fake_claude):
        _draft_reply_texts(suggestions, "test tweet", "", "@test", config)

    assert captured_kwargs.get("org_id") is None


def test_draft_reply_texts_warns_on_failure():
    """Claude failure in draft generation emits a warning, does not crash."""
    suggestions = [_make_suggestion()]
    config = VaultConfig()

    with patch("sable.shared.api.call_claude_json", side_effect=RuntimeError("API down")), \
         patch("sable.vault.suggest.logger") as mock_logger:
        result = _draft_reply_texts(suggestions, "test tweet", "testorg", "@test", config)

    assert result == suggestions  # returns suggestions unchanged
    # At least one warning should be about draft generation failure
    warning_messages = [str(c) for c in mock_logger.warning.call_args_list]
    assert any("Reply draft generation failed" in msg for msg in warning_messages)
