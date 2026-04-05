"""Tests for sable.meme.cli — Click command smoke tests."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from sable.roster.models import Account, Persona, ContentSettings


def _make_account(org: str = "testorg") -> Account:
    return Account(
        handle="@test",
        display_name="Test",
        org=org,
        persona=Persona(),
        content=ContentSettings(),
    )


class TestMemeListTemplates:
    def test_lists_templates(self, monkeypatch):
        from sable.meme.cli import meme_list_templates
        sample = [
            {
                "id": "drake",
                "name": "Drake",
                "zones": [{"id": "top"}, {"id": "bottom"}],
                "style": "classic",
                "prompt_hint": "contrast",
            }
        ]
        monkeypatch.setattr("sable.meme.templates.load_registry", lambda: sample)
        monkeypatch.setattr("sable.meme.templates.get_template_image", lambda t: None)

        runner = CliRunner()
        result = runner.invoke(meme_list_templates)
        assert result.exit_code == 0
        assert "drake" in result.output


class TestMemeGenerate:
    def test_dry_run_skips_render(self):
        acc = _make_account()
        with patch("sable.roster.manager.require_account", return_value=acc), \
             patch("sable.meme.generator.suggest_template", return_value="drake"), \
             patch("sable.meme.generator.generate_meme_text",
                   return_value={"top": "a", "bottom": "b"}), \
             patch("sable.meme.renderer.render_meme") as mock_render:

            from sable.meme.cli import meme_generate
            runner = CliRunner()
            result = runner.invoke(meme_generate,
                                   ["--account", "@test", "--dry-run"])

        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        mock_render.assert_not_called()

    def test_save_to_bank_flag(self):
        acc = _make_account(org="")
        with patch("sable.roster.manager.require_account", return_value=acc), \
             patch("sable.meme.generator.suggest_template", return_value="drake"), \
             patch("sable.meme.generator.generate_meme_text",
                   return_value={"top": "a", "bottom": "b"}), \
             patch("sable.meme.renderer.render_meme", return_value="/tmp/out.png"), \
             patch("sable.meme.bank.save_to_bank") as mock_bank:

            from sable.meme.cli import meme_generate
            runner = CliRunner()
            result = runner.invoke(meme_generate,
                                   ["--account", "@test", "--save-to-bank"])

        assert result.exit_code == 0
        mock_bank.assert_called_once()


class TestMemeSetupTemplates:
    def test_prints_instructions(self, monkeypatch):
        sample = [{"id": "drake", "name": "Drake", "image_file": "drake.jpg"}]
        monkeypatch.setattr("sable.meme.templates.load_registry", lambda: sample)
        monkeypatch.setattr("sable.meme.templates.templates_dir", lambda: "/fake/dir")

        from sable.meme.cli import meme_setup_templates
        runner = CliRunner()
        result = runner.invoke(meme_setup_templates)
        assert result.exit_code == 0
        assert "drake.jpg" in result.output
