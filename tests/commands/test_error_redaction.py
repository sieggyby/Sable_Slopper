"""Tests for CLI error redaction — exceptions containing secrets are safe to display (AUDIT-1).

Covers both rich-console and click-echo command paths.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from sable.cli import main


def test_score_command_redacts_anthropic_key_in_exception():
    """click.echo path: score command redacts ANTHROPIC_API_KEY from generic exception."""
    runner = CliRunner()

    def _boom(*a, **kw):
        raise RuntimeError("Auth failed: ANTHROPIC_API_KEY=sk-ant-secret123456789 rejected")

    with patch("sable.write.scorer.score_draft", side_effect=_boom):
        result = runner.invoke(main, ["score", "@test", "--text", "hello", "--org", "testorg"])

    assert result.exit_code != 0
    assert "sk-ant-secret123456789" not in result.output
    assert "[REDACTED]" in result.output


def test_score_command_redacts_bearer_token_in_exception():
    """click.echo path: score command redacts Bearer tokens from generic exception."""
    runner = CliRunner()

    def _boom(*a, **kw):
        raise RuntimeError("Request failed: Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.longtoken1234567890")

    with patch("sable.write.scorer.score_draft", side_effect=_boom):
        result = runner.invoke(main, ["score", "@test", "--text", "hello", "--org", "testorg"])

    assert result.exit_code != 0
    assert "eyJhbGciOiJSUzI1NiJ9" not in result.output
    assert "[REDACTED]" in result.output


def test_advise_command_redacts_secret_in_exception():
    """rich-console path: advise command redacts secrets from generic exception."""
    runner = CliRunner()

    def _boom(*a, **kw):
        raise RuntimeError("ANTHROPIC_API_KEY=sk-ant-realkey1234567890 is expired")

    with patch("sable.advise.generate.generate_advise", side_effect=_boom):
        result = runner.invoke(main, ["advise", "@test"])

    assert result.exit_code != 0
    assert "sk-ant-realkey1234567890" not in result.output
    assert "[REDACTED]" in result.output


def test_clean_exception_passes_through():
    """An exception without secrets renders its message without [REDACTED]."""
    runner = CliRunner()

    def _boom(*a, **kw):
        raise RuntimeError("SQLite error: no such table: posts")

    with patch("sable.write.scorer.score_draft", side_effect=_boom):
        result = runner.invoke(main, ["score", "@test", "--text", "hello", "--org", "testorg"])

    assert result.exit_code != 0
    assert "no such table: posts" in result.output
    assert "[REDACTED]" not in result.output


def test_write_command_redacts_secret_in_account_lookup():
    """write command's account lookup path also redacts secrets."""
    runner = CliRunner()

    def _boom(*a, **kw):
        raise ValueError("Config error: REPLICATE_API_TOKEN=r8_secretvalue12345 invalid")

    with patch("sable.roster.manager.require_account", side_effect=_boom):
        result = runner.invoke(main, ["write", "@test"])

    assert result.exit_code != 0
    assert "r8_secretvalue12345" not in result.output
    assert "[REDACTED]" in result.output


def test_score_command_redacts_xi_api_key_in_exception():
    """click.echo path: score command redacts ElevenLabs xi-api-key header values."""
    runner = CliRunner()

    def _boom(*a, **kw):
        raise RuntimeError("Request failed: xi-api-key: abc123defghij456789012345")

    with patch("sable.write.scorer.score_draft", side_effect=_boom):
        result = runner.invoke(main, ["score", "@test", "--text", "hello", "--org", "testorg"])

    assert result.exit_code != 0
    assert "abc123defghij456789012345" not in result.output
    assert "[REDACTED]" in result.output


def test_score_command_redacts_bare_replicate_token():
    """click.echo path: bare r8_ Replicate token is redacted."""
    runner = CliRunner()

    def _boom(*a, **kw):
        raise RuntimeError("Auth error with token r8_AbcDef1234567890XYZW12345")

    with patch("sable.write.scorer.score_draft", side_effect=_boom):
        result = runner.invoke(main, ["score", "@test", "--text", "hello", "--org", "testorg"])

    assert result.exit_code != 0
    assert "r8_AbcDef1234567890XYZW12345" not in result.output
    assert "[REDACTED]" in result.output


def test_onboard_command_redacts_secret_in_exception():
    """rich-console stderr path: onboard command redacts secrets."""
    runner = CliRunner()

    def _boom(*a, **kw):
        raise RuntimeError("SOCIALDATA_API_KEY=sd_realkey9876543210 unauthorized")

    with patch("sable.onboard.orchestrator.run_onboard", side_effect=_boom):
        result = runner.invoke(main, ["onboard", "test.yaml"])

    assert result.exit_code != 0
    assert "sd_realkey9876543210" not in result.output
    assert "[REDACTED]" in result.output
