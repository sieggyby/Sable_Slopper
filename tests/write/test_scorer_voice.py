"""Tests for voice_corpus parameter in score_draft."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


@patch("sable.write.scorer.call_claude_json")
@patch("sable.write.scorer.get_hook_patterns")
@patch("sable.write.scorer.require_account")
def test_voice_corpus_injected_into_prompt(mock_acc, mock_patterns, mock_claude):
    """When voice_corpus provided, it replaces tone excerpt in prompt."""
    from sable.write.scorer import score_draft, HookPattern

    acc = MagicMock()
    acc.org = "test_org"
    mock_acc.return_value = acc
    mock_patterns.return_value = [
        HookPattern(name="p1", description="d1", example="e1"),
    ]
    mock_claude.return_value = (
        '{"grade":"A","score":9,"matched_pattern":"p1","voice_fit":8,"flags":[]}'
    )

    result = score_draft(
        handle="@test",
        draft_text="test tweet",
        format_bucket="standalone_text",
        org="test_org",
        voice_corpus="## Full Voice Corpus\nDetailed voice info here",
    )

    call_args = mock_claude.call_args
    prompt = call_args[0][0] if call_args[0] else call_args.kwargs.get("prompt", "")
    assert "Full Voice Corpus" in prompt
    assert "Detailed voice info here" in prompt
    assert result.score == 9


@patch("sable.write.scorer.call_claude_json")
@patch("sable.write.scorer.get_hook_patterns")
@patch("sable.write.scorer.require_account")
def test_none_corpus_uses_tone_excerpt(mock_acc, mock_patterns, mock_claude, tmp_path):
    """When voice_corpus is None, uses 200-char tone.md excerpt."""
    from sable.write.scorer import score_draft, HookPattern

    acc = MagicMock()
    acc.org = "test_org"
    mock_acc.return_value = acc
    mock_patterns.return_value = [
        HookPattern(name="p1", description="d1", example="e1"),
    ]
    mock_claude.return_value = (
        '{"grade":"B","score":7,"matched_pattern":"p1","voice_fit":6,"flags":[]}'
    )

    tone_file = tmp_path / "tone.md"
    tone_file.write_text("Short tone excerpt for default behavior.", encoding="utf-8")

    with patch("sable.write.scorer.profile_dir", return_value=tmp_path):
        result = score_draft(
            handle="@test",
            draft_text="test tweet",
            format_bucket="standalone_text",
            org="test_org",
            voice_corpus=None,
        )

    call_args = mock_claude.call_args
    prompt = call_args[0][0] if call_args[0] else call_args.kwargs.get("prompt", "")
    assert "Short tone excerpt" in prompt
    assert "Full Voice Corpus" not in prompt
    assert result.score == 7
