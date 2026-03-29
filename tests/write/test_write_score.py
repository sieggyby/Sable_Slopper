"""Tests for `sable write --score` integration (Slice C)."""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from sable.commands.write import write_command
from sable.platform.errors import SableError


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------

@dataclass
class _FakeVariant:
    text: str = "This is hook text."
    format_fit_score: float = 8.5
    structural_move: str = "contrarian claim + specific number"
    notes: str = ""


@dataclass
class _FakeHookScore:
    grade: str = "A"
    score: float = 9.0
    matched_pattern: str | None = "Bold Claim"
    voice_fit: int = 8
    flags: list = field(default_factory=list)
    suggested_rewrite: str | None = None


@dataclass
class _FakeAccount:
    handle: str = "@testuser"
    org: str = "testorg"


def _patch_deps(monkeypatch, variants=None, score_result=None, score_side_effect=None):
    """Monkeypatch require_account, generate_tweet_variants, and score_draft."""
    if variants is None:
        variants = [_FakeVariant(), _FakeVariant()]

    acc = _FakeAccount()
    monkeypatch.setattr(
        "sable.commands.write.write_command.__wrapped__"
        if hasattr(write_command, "__wrapped__") else "sable.roster.manager.require_account",
        lambda handle: acc,
        raising=False,
    )

    import sable.roster.manager as rm
    monkeypatch.setattr(rm, "require_account", lambda handle: acc)

    import sable.write.generator as gen
    from sable.write.generator import WriteResult
    monkeypatch.setattr(gen, "generate_tweet_variants", lambda **kw: WriteResult(variants=variants))

    import sable.write.scorer as sc
    if score_side_effect is not None:
        mock_score = MagicMock(side_effect=score_side_effect)
    else:
        result = score_result if score_result is not None else _FakeHookScore()
        mock_score = MagicMock(return_value=result)
    monkeypatch.setattr(sc, "score_draft", mock_score)

    return mock_score


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_score_flag_calls_score_draft_per_variant(monkeypatch):
    mock_score = _patch_deps(monkeypatch, variants=[_FakeVariant(), _FakeVariant()])
    runner = CliRunner()
    result = runner.invoke(write_command, ["@testuser", "--score"])
    assert result.exit_code == 0, result.output
    assert mock_score.call_count == 2


def test_score_flag_output_includes_hook_grade(monkeypatch):
    _patch_deps(monkeypatch, score_result=_FakeHookScore(grade="A", score=9.0))
    runner = CliRunner()
    result = runner.invoke(write_command, ["@testuser", "--score"])
    assert result.exit_code == 0, result.output
    assert "hook: A" in result.output


def test_no_score_flag_never_calls_score_draft(monkeypatch):
    mock_score = _patch_deps(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(write_command, ["@testuser"])
    assert result.exit_code == 0, result.output
    mock_score.assert_not_called()
    assert "hook:" not in result.output


def test_score_sable_error_shows_warning_but_continues(monkeypatch):
    _patch_deps(
        monkeypatch,
        variants=[_FakeVariant(text="Variant text here.")],
        score_side_effect=SableError("NO_SCAN_DATA", "no data"),
    )
    runner = CliRunner()
    result = runner.invoke(write_command, ["@testuser", "--score"])
    assert result.exit_code == 0, result.output
    assert "hook: [error: NO_SCAN_DATA]" in result.output
    assert "Variant text here." in result.output


def test_score_generic_error_shows_warning_but_continues(monkeypatch):
    _patch_deps(
        monkeypatch,
        variants=[_FakeVariant(text="Generic error variant.")],
        score_side_effect=RuntimeError("oops"),
    )
    runner = CliRunner()
    result = runner.invoke(write_command, ["@testuser", "--score"])
    assert result.exit_code == 0, result.output
    assert "hook: [error: oops]" in result.output
    assert "Generic error variant." in result.output


def test_score_uses_explicit_format_bucket_when_provided(monkeypatch):
    mock_score = _patch_deps(monkeypatch, variants=[_FakeVariant()])
    runner = CliRunner()
    result = runner.invoke(write_command, ["@testuser", "--format", "short_clip", "--score"])
    assert result.exit_code == 0, result.output
    call_kwargs = mock_score.call_args
    assert call_kwargs.kwargs.get("format_bucket") == "short_clip"
