"""Tests for --voice-check flag wiring in write command."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from pathlib import Path

from click.testing import CliRunner

from sable.commands.write import write_command


def _make_acc():
    acc = MagicMock()
    acc.handle = "@test"
    acc.org = "test_org"
    return acc


def _make_variant():
    v = MagicMock()
    v.text = "test tweet"
    v.structural_move = "hook"
    v.format_fit_score = 8
    v.notes = ""
    return v


def _make_result(variant):
    result = MagicMock()
    result.variants = [variant]
    result.anatomy_ref = None
    result.vault_hint = None
    return result


@patch("sable.write.generator.generate_tweet_variants")
@patch("sable.write.scorer.call_claude_json")
@patch("sable.write.scorer.get_hook_patterns")
@patch("sable.write.scorer.require_account")
@patch("sable.roster.manager.require_account")
@patch("sable.write.generator.assemble_voice_corpus", return_value="voice corpus")
@patch("sable.shared.paths.vault_dir", return_value=Path("/fake/vault"))
@patch("sable.shared.paths.meta_db_path", return_value=Path("/fake/nonexistent.db"))
def test_voice_check_implies_score(mock_meta, mock_vault, mock_vc, mock_req,
                                    mock_scorer_req, mock_patterns, mock_claude,
                                    mock_gen):
    """--voice-check without --score still triggers scoring."""
    acc = _make_acc()
    mock_req.return_value = acc
    mock_scorer_req.return_value = acc
    mock_gen.return_value = _make_result(_make_variant())
    mock_patterns.return_value = []
    mock_claude.return_value = (
        '{"grade":"A","score":9,"matched_pattern":null,"voice_fit":8,"flags":[]}'
    )

    runner = CliRunner()
    result = runner.invoke(write_command, ["@test", "--voice-check"])

    assert result.exit_code == 0
    # Scoring was triggered (hook line present in output)
    assert "hook:" in result.output
    # assemble_voice_corpus was called
    mock_vc.assert_called_once()


@patch("sable.write.generator.generate_tweet_variants")
@patch("sable.roster.manager.require_account")
@patch("sable.shared.paths.vault_dir", return_value=Path("/fake/vault"))
@patch("sable.shared.paths.meta_db_path", return_value=Path("/fake/nonexistent.db"))
def test_no_voice_check_no_corpus(mock_meta, mock_vault, mock_req, mock_gen):
    """Without --voice-check, assemble_voice_corpus is not called."""
    acc = _make_acc()
    mock_req.return_value = acc
    mock_gen.return_value = _make_result(_make_variant())

    runner = CliRunner()
    with patch("sable.write.generator.assemble_voice_corpus") as mock_vc:
        result = runner.invoke(write_command, ["@test"])

    mock_vc.assert_not_called()
    assert result.exit_code == 0
