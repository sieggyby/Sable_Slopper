"""Tests for meme artifact registration integration."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


def test_meme_generate_registers_artifact():
    """After meme render, artifact is registered when org is available."""
    from click.testing import CliRunner
    from sable.meme.cli import meme_generate
    from sable.roster.models import Account, Persona, ContentSettings

    acc = Account(
        handle="@test",
        display_name="Test",
        org="psy",
        persona=Persona(),
        content=ContentSettings(),
    )
    mock_register = MagicMock()

    with patch("sable.roster.manager.require_account", return_value=acc), \
         patch("sable.meme.generator.suggest_template", return_value="drake"), \
         patch("sable.meme.generator.generate_meme_text", return_value={"top": "a", "bottom": "b"}), \
         patch("sable.meme.renderer.render_meme", return_value="/tmp/drake_123.png"), \
         patch("sable.platform.artifacts.register_content_artifact", mock_register):
        runner = CliRunner()
        result = runner.invoke(meme_generate, ["--account", "@test"])

    assert result.exit_code == 0, result.output
    mock_register.assert_called_once()
    args, kwargs = mock_register.call_args
    assert kwargs["org_id"] == "psy"
    assert kwargs["artifact_type"] == "content_meme"
    assert kwargs["path"] == "/tmp/drake_123.png"


def test_meme_generate_skips_artifact_when_no_org():
    """When account has no org, artifact registration is skipped."""
    from click.testing import CliRunner
    from sable.meme.cli import meme_generate
    from sable.roster.models import Account, Persona, ContentSettings

    acc = Account(
        handle="@test",
        display_name="Test",
        org="",
        persona=Persona(),
        content=ContentSettings(),
    )
    mock_register = MagicMock()

    with patch("sable.roster.manager.require_account", return_value=acc), \
         patch("sable.meme.generator.suggest_template", return_value="drake"), \
         patch("sable.meme.generator.generate_meme_text", return_value={"top": "a", "bottom": "b"}), \
         patch("sable.meme.renderer.render_meme", return_value="/tmp/drake_123.png"), \
         patch("sable.platform.artifacts.register_content_artifact", mock_register):
        runner = CliRunner()
        result = runner.invoke(meme_generate, ["--account", "@test"])

    assert result.exit_code == 0, result.output
    mock_register.assert_not_called()
