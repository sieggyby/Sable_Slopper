"""Tests for --lexicon flag integration in write command."""
from __future__ import annotations

from unittest.mock import patch, MagicMock


@patch("sable.write.generator.call_claude_json")
def test_lexicon_terms_injected_into_prompt(mock_claude):
    """When lexicon_terms provided, community vocabulary appears in the prompt."""
    mock_claude.return_value = '{"variants": [{"text": "test", "structural_move": "hook", "format_fit_score": 8}]}'

    from sable.write.generator import generate_tweet_variants

    terms = [
        {"term": "zkrollup", "gloss": "ZK tech"},
        {"term": "gm", "gloss": "Good morning"},
    ]

    with patch("sable.write.generator.require_account") as mock_acc, \
         patch("sable.write.generator.build_account_context", return_value="test context"):
        acc = MagicMock()
        acc.handle = "@test"
        acc.org = "test_org"
        mock_acc.return_value = acc

        generate_tweet_variants(
            handle="@test",
            org="test_org",
            format_bucket="standalone_text",
            topic="test",
            source_url=None,
            num_variants=1,
            meta_db_path=None,
            vault_root=None,
            lexicon_terms=terms,
        )

    # Verify the prompt included lexicon vocabulary
    call_args = mock_claude.call_args
    prompt = call_args.kwargs.get("prompt", call_args[0][0] if call_args[0] else "")
    assert "Community vocabulary" in prompt
    assert "zkrollup" in prompt
    assert "ZK tech" in prompt


@patch("sable.write.generator.call_claude_json")
def test_no_lexicon_terms_no_block(mock_claude):
    """When lexicon_terms is None, no vocabulary block in prompt."""
    mock_claude.return_value = '{"variants": [{"text": "test", "structural_move": "hook", "format_fit_score": 8}]}'

    from sable.write.generator import generate_tweet_variants

    with patch("sable.write.generator.require_account") as mock_acc, \
         patch("sable.write.generator.build_account_context", return_value="test context"):
        acc = MagicMock()
        acc.handle = "@test"
        acc.org = "test_org"
        mock_acc.return_value = acc

        generate_tweet_variants(
            handle="@test",
            org="test_org",
            format_bucket="standalone_text",
            topic="test",
            source_url=None,
            num_variants=1,
            meta_db_path=None,
            vault_root=None,
            lexicon_terms=None,
        )

    call_args = mock_claude.call_args
    prompt = call_args.kwargs.get("prompt", call_args[0][0] if call_args[0] else "")
    assert "Community vocabulary" not in prompt
